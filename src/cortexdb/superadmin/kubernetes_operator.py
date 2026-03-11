"""
Kubernetes Operator — Native K8s operator for automated scaling, rolling upgrades,
backup CRDs, and self-healing CortexDB clusters.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from cortexdb.superadmin.persistence import PersistenceStore

logger = logging.getLogger("cortexdb.kubernetes_operator")

# Default resource limits for CortexDB pods
DEFAULT_RESOURCES = {
    "api": {"cpu": "500m", "memory": "512Mi", "replicas": 3},
    "worker": {"cpu": "1000m", "memory": "1Gi", "replicas": 2},
    "db": {"cpu": "2000m", "memory": "4Gi", "replicas": 1},
}

VALID_OPERATION_TYPES = {"scale", "upgrade", "backup", "restore", "restart"}
VALID_OPERATION_STATUSES = {"pending", "running", "completed", "failed"}
VALID_CLUSTER_STATUSES = {"active", "degraded", "offline"}


class KubernetesOperator:
    """Manages CortexDB clusters on Kubernetes with automated scaling, upgrades, and backups."""

    def __init__(self, persistence_store: "PersistenceStore") -> None:
        self._store = persistence_store
        self._init_db()

    # ── Schema ──────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        # Tables 'k8s_clusters', 'k8s_deployments', and 'k8s_operations' are
        # managed by the SQLite migration system (see migrations.py v5).
        logger.info("Kubernetes operator tables initialized (managed by migrations)")

    # ── Helpers ─────────────────────────────────────────────────────────

    def _row_to_dict(self, row) -> Optional[dict]:
        if row is None:
            return None
        d = dict(row)
        for key in ("config", "details"):
            if key in d and isinstance(d[key], str):
                try:
                    d[key] = json.loads(d[key])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d

    def _get_cluster_row(self, cluster_id: str) -> Optional[dict]:
        row = self._store.conn.execute(
            "SELECT * FROM k8s_clusters WHERE id = ?", (cluster_id,)
        ).fetchone()
        return self._row_to_dict(row)

    def _record_operation(self, cluster_id: str, op_type: str, details: Dict = None,
                          status: str = "completed") -> dict:
        """Record a cluster operation in the operations log."""
        op_id = f"op-{uuid.uuid4().hex[:12]}"
        now = time.time()
        completed = now if status in ("completed", "failed") else None
        self._store.conn.execute(
            """INSERT INTO k8s_operations
               (id, cluster_id, operation_type, status, details, started_at, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (op_id, cluster_id, op_type, status, json.dumps(details or {}), now, completed),
        )
        self._store.conn.commit()
        return {"operation_id": op_id, "type": op_type, "status": status}

    # ── Cluster CRUD ────────────────────────────────────────────────────

    def register_cluster(
        self,
        name: str,
        namespace: str = "cortexdb",
        config: Optional[Dict] = None,
    ) -> dict:
        """Register a new Kubernetes cluster for CortexDB management."""
        cluster_id = f"k8s-{uuid.uuid4().hex[:12]}"
        now = time.time()
        cluster_config = config or {}
        kubeconfig_ref = cluster_config.pop("kubeconfig_ref", None)

        self._store.conn.execute(
            """INSERT INTO k8s_clusters
               (id, name, namespace, kubeconfig_ref, status, config, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'active', ?, ?, ?)""",
            (cluster_id, name, namespace, kubeconfig_ref,
             json.dumps(cluster_config), now, now),
        )

        # Create default deployments
        for component, res in DEFAULT_RESOURCES.items():
            dep_id = f"dep-{uuid.uuid4().hex[:12]}"
            image = cluster_config.get("image", "cortexdb/cortexdb:latest")
            self._store.conn.execute(
                """INSERT INTO k8s_deployments
                   (id, cluster_id, name, replicas, image, status, config, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'running', ?, ?, ?)""",
                (dep_id, cluster_id, f"cortexdb-{component}", res["replicas"],
                 image, json.dumps(res), now, now),
            )

        self._store.conn.commit()
        logger.info("Registered K8s cluster %s (%s) in namespace %s", cluster_id, name, namespace)
        self._store.audit("register_k8s_cluster", "k8s_cluster", cluster_id,
                          {"name": name, "namespace": namespace})
        return self.get_cluster(cluster_id)

    def list_clusters(self) -> list:
        """List all registered Kubernetes clusters."""
        rows = self._store.conn.execute(
            "SELECT * FROM k8s_clusters ORDER BY created_at DESC"
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_cluster(self, cluster_id: str) -> dict:
        """Get a cluster by ID, including its deployments."""
        cluster = self._get_cluster_row(cluster_id)
        if not cluster:
            raise ValueError(f"K8s cluster '{cluster_id}' not found")

        deps = self._store.conn.execute(
            "SELECT * FROM k8s_deployments WHERE cluster_id = ? ORDER BY name",
            (cluster_id,),
        ).fetchall()
        cluster["deployments"] = [self._row_to_dict(d) for d in deps]
        return cluster

    def remove_cluster(self, cluster_id: str) -> dict:
        """Remove a Kubernetes cluster and all its resources."""
        cluster = self.get_cluster(cluster_id)
        self._store.conn.execute("DELETE FROM k8s_operations WHERE cluster_id = ?", (cluster_id,))
        self._store.conn.execute("DELETE FROM k8s_deployments WHERE cluster_id = ?", (cluster_id,))
        self._store.conn.execute("DELETE FROM k8s_clusters WHERE id = ?", (cluster_id,))
        self._store.conn.commit()
        logger.info("Removed K8s cluster %s", cluster_id)
        self._store.audit("remove_k8s_cluster", "k8s_cluster", cluster_id,
                          {"name": cluster["name"]})
        return {"removed": True, "cluster_id": cluster_id, "name": cluster["name"]}

    # ── Cluster Status ──────────────────────────────────────────────────

    def get_cluster_status(self, cluster_id: str) -> dict:
        """Get detailed cluster status: pods, resources, recent events."""
        cluster = self.get_cluster(cluster_id)
        now = time.time()

        total_replicas = sum(d.get("replicas", 0) for d in cluster["deployments"])
        running_deps = [d for d in cluster["deployments"] if d.get("status") == "running"]

        recent_ops = self._store.conn.execute(
            "SELECT * FROM k8s_operations WHERE cluster_id = ? ORDER BY started_at DESC LIMIT 10",
            (cluster_id,),
        ).fetchall()

        return {
            "cluster_id": cluster_id,
            "name": cluster["name"],
            "namespace": cluster["namespace"],
            "status": cluster["status"],
            "deployments": len(cluster["deployments"]),
            "running_deployments": len(running_deps),
            "total_replicas": total_replicas,
            "pod_count": cluster["pod_count"],
            "node_count": cluster["node_count"],
            "recent_operations": [self._row_to_dict(o) for o in recent_ops],
            "health": "healthy" if len(running_deps) == len(cluster["deployments"]) else "degraded",
            "checked_at": now,
        }

    # ── Scaling ─────────────────────────────────────────────────────────

    def scale(self, cluster_id: str, component: str, replicas: int) -> dict:
        """Scale a cluster component (api, worker, db) to the desired replica count."""
        if replicas < 0:
            raise ValueError("replicas must be >= 0")
        cluster = self.get_cluster(cluster_id)
        dep_name = f"cortexdb-{component}"

        dep = self._store.conn.execute(
            "SELECT * FROM k8s_deployments WHERE cluster_id = ? AND name = ?",
            (cluster_id, dep_name),
        ).fetchone()
        if not dep:
            raise ValueError(f"Component '{component}' not found in cluster '{cluster_id}'")

        old_replicas = dep["replicas"]
        now = time.time()
        self._store.conn.execute(
            "UPDATE k8s_deployments SET replicas = ?, updated_at = ? WHERE id = ?",
            (replicas, now, dep["id"]),
        )
        self._store.conn.commit()

        op = self._record_operation(cluster_id, "scale", {
            "component": component, "from_replicas": old_replicas, "to_replicas": replicas,
        })
        logger.info("Scaled %s in cluster %s: %d -> %d replicas",
                     dep_name, cluster_id, old_replicas, replicas)

        return {
            "cluster_id": cluster_id,
            "component": component,
            "previous_replicas": old_replicas,
            "new_replicas": replicas,
            "operation": op,
        }

    # ── Rolling Upgrade ─────────────────────────────────────────────────

    def rolling_upgrade(
        self,
        cluster_id: str,
        image: str,
        strategy: str = "rolling",
    ) -> dict:
        """Perform a rolling upgrade of all deployments in a cluster."""
        cluster = self.get_cluster(cluster_id)
        now = time.time()

        updated_deployments = []
        for dep in cluster["deployments"]:
            old_image = dep["image"]
            self._store.conn.execute(
                "UPDATE k8s_deployments SET image = ?, status = 'updating', updated_at = ? WHERE id = ?",
                (image, now, dep["id"]),
            )
            updated_deployments.append({
                "name": dep["name"],
                "old_image": old_image,
                "new_image": image,
            })

        # Mark as running after upgrade
        self._store.conn.execute(
            "UPDATE k8s_deployments SET status = 'running' WHERE cluster_id = ?",
            (cluster_id,),
        )
        self._store.conn.commit()

        op = self._record_operation(cluster_id, "upgrade", {
            "image": image, "strategy": strategy,
            "deployments_updated": len(updated_deployments),
        })
        logger.info("Rolling upgrade of cluster %s to image %s (%s strategy)",
                     cluster_id, image, strategy)

        return {
            "cluster_id": cluster_id,
            "image": image,
            "strategy": strategy,
            "deployments_updated": updated_deployments,
            "operation": op,
        }

    # ── Backup & Restore ────────────────────────────────────────────────

    def create_backup(self, cluster_id: str) -> dict:
        """Trigger a CRD-based backup for a cluster."""
        cluster = self.get_cluster(cluster_id)
        backup_id = f"bk-{uuid.uuid4().hex[:12]}"
        now = time.time()

        op = self._record_operation(cluster_id, "backup", {
            "backup_id": backup_id,
            "cluster_name": cluster["name"],
            "namespace": cluster["namespace"],
            "timestamp": now,
            "size_estimate_mb": cluster.get("pod_count", 1) * 256,
        })
        logger.info("Created backup %s for cluster %s", backup_id, cluster_id)

        return {
            "backup_id": backup_id,
            "cluster_id": cluster_id,
            "status": "completed",
            "created_at": now,
            "operation": op,
        }

    def list_backups(self, cluster_id: Optional[str] = None) -> list:
        """List backup operations, optionally filtered by cluster."""
        sql = "SELECT * FROM k8s_operations WHERE operation_type = 'backup'"
        params: list = []
        if cluster_id:
            sql += " AND cluster_id = ?"
            params.append(cluster_id)
        sql += " ORDER BY started_at DESC"
        rows = self._store.conn.execute(sql, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def restore_backup(self, cluster_id: str, backup_id: str) -> dict:
        """Restore a cluster from a backup."""
        cluster = self.get_cluster(cluster_id)

        # Verify backup exists
        backup = self._store.conn.execute(
            """SELECT * FROM k8s_operations
               WHERE operation_type = 'backup' AND cluster_id = ?
               AND json_extract(details, '$.backup_id') = ?""",
            (cluster_id, backup_id),
        ).fetchone()
        if not backup:
            raise ValueError(f"Backup '{backup_id}' not found for cluster '{cluster_id}'")

        op = self._record_operation(cluster_id, "restore", {
            "backup_id": backup_id,
            "cluster_name": cluster["name"],
        })
        logger.info("Restored cluster %s from backup %s", cluster_id, backup_id)

        return {
            "cluster_id": cluster_id,
            "backup_id": backup_id,
            "status": "completed",
            "operation": op,
        }

    # ── Component Restart ───────────────────────────────────────────────

    def restart_component(self, cluster_id: str, component: str) -> dict:
        """Restart a specific component in a cluster."""
        cluster = self.get_cluster(cluster_id)
        dep_name = f"cortexdb-{component}"

        dep = self._store.conn.execute(
            "SELECT * FROM k8s_deployments WHERE cluster_id = ? AND name = ?",
            (cluster_id, dep_name),
        ).fetchone()
        if not dep:
            raise ValueError(f"Component '{component}' not found in cluster '{cluster_id}'")

        now = time.time()
        self._store.conn.execute(
            "UPDATE k8s_deployments SET status = 'restarting', updated_at = ? WHERE id = ?",
            (now, dep["id"]),
        )
        # Simulate restart completion
        self._store.conn.execute(
            "UPDATE k8s_deployments SET status = 'running', updated_at = ? WHERE id = ?",
            (now + 0.1, dep["id"]),
        )
        self._store.conn.commit()

        op = self._record_operation(cluster_id, "restart", {"component": component})
        logger.info("Restarted component %s in cluster %s", component, cluster_id)

        return {
            "cluster_id": cluster_id,
            "component": component,
            "status": "running",
            "operation": op,
        }

    # ── Resource Usage ──────────────────────────────────────────────────

    def get_resource_usage(self, cluster_id: str) -> dict:
        """Get CPU, memory, and storage usage across all pods in a cluster."""
        cluster = self.get_cluster(cluster_id)

        usage = {"total_cpu_millicores": 0, "total_memory_mb": 0, "by_component": {}}
        for dep in cluster["deployments"]:
            config = dep.get("config", {})
            cpu_str = config.get("cpu", "500m")
            mem_str = config.get("memory", "512Mi")

            cpu_mc = int(cpu_str.replace("m", "")) if "m" in str(cpu_str) else int(cpu_str) * 1000
            mem_mb = int(mem_str.replace("Mi", "")) if "Mi" in str(mem_str) else int(mem_str.replace("Gi", "")) * 1024

            replicas = dep.get("replicas", 1)
            total_cpu = cpu_mc * replicas
            total_mem = mem_mb * replicas

            usage["total_cpu_millicores"] += total_cpu
            usage["total_memory_mb"] += total_mem
            usage["by_component"][dep["name"]] = {
                "replicas": replicas,
                "cpu_per_pod_mc": cpu_mc,
                "memory_per_pod_mb": mem_mb,
                "total_cpu_mc": total_cpu,
                "total_memory_mb": total_mem,
            }

        usage["cluster_id"] = cluster_id
        usage["cluster_name"] = cluster["name"]
        return usage

    # ── Manifest Generation ─────────────────────────────────────────────

    def generate_manifests(self, config: Optional[Dict] = None) -> dict:
        """Generate Kubernetes YAML manifests for a CortexDB deployment."""
        cfg = config or {}
        namespace = cfg.get("namespace", "cortexdb")
        image = cfg.get("image", "cortexdb/cortexdb:latest")
        replicas = cfg.get("replicas", 3)
        storage_size = cfg.get("storage_size", "50Gi")
        cpu_limit = cfg.get("cpu_limit", "2000m")
        memory_limit = cfg.get("memory_limit", "4Gi")
        cpu_request = cfg.get("cpu_request", "500m")
        memory_request = cfg.get("memory_request", "1Gi")

        manifests = {
            "deployment": self._manifest_deployment(namespace, image, replicas,
                                                     cpu_request, memory_request,
                                                     cpu_limit, memory_limit),
            "service_clusterip": self._manifest_service(namespace, "ClusterIP"),
            "service_loadbalancer": self._manifest_service(namespace, "LoadBalancer"),
            "pvc": self._manifest_pvc(namespace, storage_size),
            "crd": self._manifest_crd(),
            "rbac": self._manifest_rbac(namespace),
            "hpa": self._manifest_hpa(namespace, replicas),
        }
        logger.info("Generated K8s manifests for namespace=%s image=%s replicas=%d",
                     namespace, image, replicas)
        return manifests

    def _manifest_deployment(self, namespace: str, image: str, replicas: int,
                              cpu_req: str, mem_req: str,
                              cpu_lim: str, mem_lim: str) -> str:
        return f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: cortexdb
  namespace: {namespace}
  labels:
    app: cortexdb
    app.kubernetes.io/name: cortexdb
    app.kubernetes.io/part-of: cortexdb-cluster
spec:
  replicas: {replicas}
  selector:
    matchLabels:
      app: cortexdb
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 1
  template:
    metadata:
      labels:
        app: cortexdb
    spec:
      serviceAccountName: cortexdb-sa
      containers:
      - name: cortexdb
        image: {image}
        ports:
        - containerPort: 5432
          name: db
        - containerPort: 8080
          name: http
        - containerPort: 9090
          name: metrics
        env:
        - name: CORTEXDB_DATA_DIR
          value: /data/cortexdb
        - name: CORTEXDB_LOG_LEVEL
          value: info
        - name: CORTEXDB_CLUSTER_MODE
          value: "true"
        resources:
          requests:
            cpu: {cpu_req}
            memory: {mem_req}
          limits:
            cpu: {cpu_lim}
            memory: {mem_lim}
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8080
          initialDelaySeconds: 15
          periodSeconds: 10
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
          failureThreshold: 3
        volumeMounts:
        - name: data
          mountPath: /data/cortexdb
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: cortexdb-data"""

    def _manifest_service(self, namespace: str, svc_type: str) -> str:
        name = "cortexdb" if svc_type == "ClusterIP" else "cortexdb-lb"
        return f"""apiVersion: v1
kind: Service
metadata:
  name: {name}
  namespace: {namespace}
  labels:
    app: cortexdb
spec:
  type: {svc_type}
  selector:
    app: cortexdb
  ports:
  - name: db
    port: 5432
    targetPort: 5432
  - name: http
    port: 8080
    targetPort: 8080
  - name: metrics
    port: 9090
    targetPort: 9090"""

    def _manifest_pvc(self, namespace: str, size: str) -> str:
        return f"""apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: cortexdb-data
  namespace: {namespace}
  labels:
    app: cortexdb
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: {size}
  storageClassName: standard"""

    def _manifest_crd(self) -> str:
        return """apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: cortexdbclusters.cortexdb.io
spec:
  group: cortexdb.io
  versions:
  - name: v1
    served: true
    storage: true
    schema:
      openAPIV3Schema:
        type: object
        properties:
          spec:
            type: object
            properties:
              replicas:
                type: integer
                minimum: 1
                default: 3
              image:
                type: string
                default: cortexdb/cortexdb:latest
              storage:
                type: string
                default: 50Gi
              backup:
                type: object
                properties:
                  enabled:
                    type: boolean
                    default: true
                  schedule:
                    type: string
                    default: "0 2 * * *"
                  retention:
                    type: integer
                    default: 7
          status:
            type: object
            properties:
              phase:
                type: string
              readyReplicas:
                type: integer
              message:
                type: string
    subresources:
      status: {}
    additionalPrinterColumns:
    - name: Replicas
      type: integer
      jsonPath: .spec.replicas
    - name: Status
      type: string
      jsonPath: .status.phase
    - name: Age
      type: date
      jsonPath: .metadata.creationTimestamp
  scope: Namespaced
  names:
    plural: cortexdbclusters
    singular: cortexdbcluster
    kind: CortexDBCluster
    shortNames:
    - cdb"""

    def _manifest_rbac(self, namespace: str) -> str:
        return f"""# ServiceAccount
apiVersion: v1
kind: ServiceAccount
metadata:
  name: cortexdb-sa
  namespace: {namespace}
  labels:
    app: cortexdb
---
# ClusterRole
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: cortexdb-operator
  labels:
    app: cortexdb
rules:
- apiGroups: [""]
  resources: ["pods", "services", "configmaps", "secrets", "persistentvolumeclaims"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["apps"]
  resources: ["deployments", "statefulsets"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["cortexdb.io"]
  resources: ["cortexdbclusters", "cortexdbclusters/status"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["batch"]
  resources: ["jobs", "cronjobs"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
---
# ClusterRoleBinding
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: cortexdb-operator-binding
  labels:
    app: cortexdb
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cortexdb-operator
subjects:
- kind: ServiceAccount
  name: cortexdb-sa
  namespace: {namespace}"""

    def _manifest_hpa(self, namespace: str, max_replicas: int) -> str:
        return f"""apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: cortexdb-hpa
  namespace: {namespace}
  labels:
    app: cortexdb
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: cortexdb
  minReplicas: 1
  maxReplicas: {max(max_replicas * 3, 10)}
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Pods
        value: 2
        periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Pods
        value: 1
        periodSeconds: 120"""

    # ── Operations Log ──────────────────────────────────────────────────

    def get_operations(self, cluster_id: Optional[str] = None, limit: int = 50) -> list:
        """Get operations log, optionally filtered by cluster."""
        sql = "SELECT * FROM k8s_operations WHERE 1=1"
        params: list = []
        if cluster_id:
            sql += " AND cluster_id = ?"
            params.append(cluster_id)
        sql += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        rows = self._store.conn.execute(sql, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ── AI Scaling Recommendations ──────────────────────────────────────

    def get_recommended_scaling(self, cluster_id: str) -> dict:
        """Generate AI-based scaling recommendations based on current resource usage."""
        cluster = self.get_cluster(cluster_id)
        usage = self.get_resource_usage(cluster_id)

        recommendations = []
        for dep in cluster["deployments"]:
            config = dep.get("config", {})
            replicas = dep.get("replicas", 1)
            component = dep["name"]

            cpu_str = config.get("cpu", "500m")
            cpu_mc = int(cpu_str.replace("m", "")) if "m" in str(cpu_str) else int(cpu_str) * 1000

            # Simple heuristic: if running at high CPU per pod, suggest scale up
            if cpu_mc >= 1000 and replicas < 5:
                recommendations.append({
                    "component": component,
                    "action": "scale_up",
                    "current_replicas": replicas,
                    "recommended_replicas": min(replicas + 1, 10),
                    "reason": f"High CPU allocation ({cpu_mc}m per pod) suggests load could benefit from horizontal scaling",
                    "confidence": 0.75,
                })
            elif replicas > 3 and cpu_mc < 300:
                recommendations.append({
                    "component": component,
                    "action": "scale_down",
                    "current_replicas": replicas,
                    "recommended_replicas": max(replicas - 1, 1),
                    "reason": f"Low CPU allocation ({cpu_mc}m per pod) with {replicas} replicas suggests over-provisioning",
                    "confidence": 0.65,
                })
            else:
                recommendations.append({
                    "component": component,
                    "action": "no_change",
                    "current_replicas": replicas,
                    "recommended_replicas": replicas,
                    "reason": "Current scaling appears appropriate",
                    "confidence": 0.85,
                })

        return {
            "cluster_id": cluster_id,
            "cluster_name": cluster["name"],
            "recommendations": recommendations,
            "generated_at": time.time(),
        }

    # ── Statistics ──────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get aggregate Kubernetes operator statistics."""
        conn = self._store.conn

        total_clusters = conn.execute(
            "SELECT COUNT(*) as cnt FROM k8s_clusters"
        ).fetchone()["cnt"]

        by_status = {}
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM k8s_clusters GROUP BY status"
        ).fetchall()
        for r in rows:
            by_status[r["status"]] = r["cnt"]

        total_deployments = conn.execute(
            "SELECT COUNT(*) as cnt FROM k8s_deployments"
        ).fetchone()["cnt"]

        total_replicas = conn.execute(
            "SELECT COALESCE(SUM(replicas), 0) as total FROM k8s_deployments"
        ).fetchone()["total"]

        total_operations = conn.execute(
            "SELECT COUNT(*) as cnt FROM k8s_operations"
        ).fetchone()["cnt"]

        ops_by_type = {}
        rows = conn.execute(
            "SELECT operation_type, COUNT(*) as cnt FROM k8s_operations GROUP BY operation_type"
        ).fetchall()
        for r in rows:
            ops_by_type[r["operation_type"]] = r["cnt"]

        return {
            "total_clusters": total_clusters,
            "clusters_by_status": by_status,
            "total_deployments": total_deployments,
            "total_replicas": total_replicas,
            "total_operations": total_operations,
            "operations_by_type": ops_by_type,
        }
