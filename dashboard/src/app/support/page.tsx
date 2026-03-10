'use client';

import { LifeBuoy, MessageCircle, BookOpen, Bug, HelpCircle, ChevronRight, ExternalLink, Mail, Github } from 'lucide-react';
import { AppShell } from '@/components/shell/AppShell';
import { GlassCard } from '@/components/shared/GlassCard';
import { useState } from 'react';

const FAQ: Array<{ q: string; a: string }> = [
  { q: 'How do I reset a stuck engine?', a: 'Use the Grid self-healing page or call POST /v1/grid/repair/{node_id}. The Autonomic Regulator also auto-detects and recovers stuck engines within 30 seconds.' },
  { q: 'Can I use standard SQL with CortexDB?', a: 'Yes. Standard SQL queries are fully supported and routed to RelationalCore (PostgreSQL). CortexQL extends SQL with FIND SIMILAR, TRAVERSE, SUBSCRIBE, and COMMIT TO LEDGER syntax.' },
  { q: 'How does tenant data isolation work?', a: 'CortexDB uses PostgreSQL Row-Level Security (RLS) with automatic tenant_id injection. Each tenant has per-tenant encryption keys (AES-256-GCM). Citus co-locates tenant data on the same shard for efficient JOINs.' },
  { q: 'What happens during a Sleep Cycle?', a: 'The Sleep Cycle runs nightly at 3 AM. It vacuums tables, rebuilds indexes, consolidates cache, archives old audit logs, and runs compliance verification. All operations are non-blocking.' },
  { q: 'How do I add a new Citus worker?', a: 'Call POST /v1/admin/sharding/add-worker with the worker hostname/port. Then call POST /v1/admin/sharding/rebalance to redistribute shards. Zero downtime.' },
  { q: 'Is CortexDB suitable for real-time analytics?', a: 'Yes. TemporalCore handles time-series data with automatic time_bucket aggregation, continuous aggregates, and data retention policies. StreamCore provides real-time event streaming with consumer groups.' },
  { q: 'How does the Read Cascade improve performance?', a: 'The 5-tier cascade (R0 Process → R1 Redis → R2 Semantic → R3 PostgreSQL → R4 Deep) achieves 75-85% cache hit rates. R0 process cache responds in <0.1ms. Cache invalidation is automatic on writes.' },
  { q: 'What embedding models are supported?', a: 'CortexDB supports any sentence-transformers model. Default is all-MiniLM-L6-v2. Configure via EMBEDDING_MODEL env var. Custom models can be loaded from local paths or HuggingFace.' },
];

const TROUBLESHOOTING = [
  { issue: 'Engine shows "down" status', solution: 'Check Docker container: docker compose logs <service>. Verify connection string in .env. The Grid will auto-repair within 60s if the container is healthy.' },
  { issue: 'High memory usage', solution: 'Check Redis maxmemory setting. Review R0 process cache size (PROCESS_CACHE_MAX env var). Run Sleep Cycle manually: POST /v1/admin/sleep-cycle/run.' },
  { issue: 'Slow vector queries', solution: 'Ensure Qdrant has enough RAM for HNSW index. Check vector dimensions match embedding model. Index rebuild: POST /v1/admin/indexes/create.' },
  { issue: 'Compliance audit fails', solution: 'Run POST /v1/compliance/encryption/rotate-keys if keys are expired. Check audit log integrity. Review GET /v1/compliance/audit/{framework} for specific control failures.' },
  { issue: 'Dashboard can\'t connect', solution: 'Verify NEXT_PUBLIC_API_URL in .env.local. Check CORS settings on the server. Ensure cortexdb-server container is running on port 5400.' },
];

export default function SupportPage() {
  const [expandedFaq, setExpandedFaq] = useState<number | null>(null);
  const [expandedTs, setExpandedTs] = useState<number | null>(null);

  return (
    <AppShell title="Support" icon={LifeBuoy} color="#FB7185">
      <div className="mb-6">
        <h2 className="text-xl font-semibold mb-1">Support Center</h2>
        <p className="text-sm text-white/40">FAQ, troubleshooting, documentation, and contact</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6">
        <div>
          {/* FAQ */}
          <h3 className="text-base font-semibold mb-3 text-white/80">
            <HelpCircle className="w-4 h-4 inline mr-1.5" /> Frequently Asked Questions
          </h3>
          <div className="space-y-2 mb-8">
            {FAQ.map((faq, i) => (
              <GlassCard key={i} hover onClick={() => setExpandedFaq(expandedFaq === i ? null : i)}>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{faq.q}</span>
                  <ChevronRight className={`w-4 h-4 text-white/30 shrink-0 transition-transform ${expandedFaq === i ? 'rotate-90' : ''}`} />
                </div>
                {expandedFaq === i && (
                  <div className="mt-3 text-sm text-white/50 leading-relaxed border-t border-white/5 pt-3">
                    {faq.a}
                  </div>
                )}
              </GlassCard>
            ))}
          </div>

          {/* Troubleshooting */}
          <h3 className="text-base font-semibold mb-3 text-white/80">
            <Bug className="w-4 h-4 inline mr-1.5" /> Troubleshooting
          </h3>
          <div className="space-y-2">
            {TROUBLESHOOTING.map((ts, i) => (
              <GlassCard key={i} hover onClick={() => setExpandedTs(expandedTs === i ? null : i)}>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-amber-400">{ts.issue}</span>
                </div>
                {expandedTs === i && (
                  <div className="mt-3 text-sm text-white/50 leading-relaxed border-t border-white/5 pt-3">
                    {ts.solution}
                  </div>
                )}
              </GlassCard>
            ))}
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          {/* Quick Links */}
          <GlassCard>
            <h3 className="text-sm font-semibold mb-3">Documentation</h3>
            <div className="space-y-2">
              {[
                { name: 'White Paper', desc: 'Architecture deep-dive', href: '/docs/WHITEPAPER.md' },
                { name: 'Developer Guide', desc: 'Complete API reference', href: '/docs/DEVELOPER-GUIDE.md' },
                { name: 'Docker Guide', desc: 'Deployment & scaling', href: '/docs/DOCKER-GUIDE.md' },
                { name: 'Use Cases', desc: 'Industry implementations', href: '/docs/USE-CASES.md' },
              ].map((doc) => (
                <div key={doc.name} className="flex items-center justify-between py-1.5 text-sm">
                  <div>
                    <div className="text-white/70">{doc.name}</div>
                    <div className="text-[10px] text-white/30">{doc.desc}</div>
                  </div>
                  <BookOpen className="w-3.5 h-3.5 text-white/20" />
                </div>
              ))}
            </div>
          </GlassCard>

          {/* Contact */}
          <GlassCard>
            <h3 className="text-sm font-semibold mb-3">Contact</h3>
            <div className="space-y-3 text-sm">
              <div className="flex items-center gap-2 text-white/50">
                <Mail className="w-4 h-4 text-white/30" />
                <span>support@nirlab.ai</span>
              </div>
              <div className="flex items-center gap-2 text-white/50">
                <Github className="w-4 h-4 text-white/30" />
                <span>github.com/nirlab/cortexdb</span>
              </div>
              <div className="flex items-center gap-2 text-white/50">
                <MessageCircle className="w-4 h-4 text-white/30" />
                <span>Discord Community</span>
              </div>
            </div>
          </GlassCard>

          {/* Version Info */}
          <GlassCard>
            <h3 className="text-sm font-semibold mb-3">System Info</h3>
            <div className="space-y-1.5 text-xs text-white/40">
              <div className="flex justify-between"><span>CortexDB</span><span className="text-white/60">v4.0.0</span></div>
              <div className="flex justify-between"><span>PostgreSQL</span><span className="text-white/60">16.2</span></div>
              <div className="flex justify-between"><span>Citus</span><span className="text-white/60">12.1</span></div>
              <div className="flex justify-between"><span>Redis</span><span className="text-white/60">7.2</span></div>
              <div className="flex justify-between"><span>Qdrant</span><span className="text-white/60">1.12</span></div>
              <div className="flex justify-between"><span>Python</span><span className="text-white/60">3.12</span></div>
              <div className="flex justify-between"><span>Dashboard</span><span className="text-white/60">Next.js 15</span></div>
            </div>
          </GlassCard>
        </div>
      </div>
    </AppShell>
  );
}
