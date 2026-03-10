/**
 * @cortexdb/client - Node.js/TypeScript client for CortexDB
 * npm install @cortexdb/client
 *
 * @example
 * ```ts
 * import { CortexDBClient } from "@cortexdb/client";
 *
 * const client = new CortexDBClient("http://localhost:5400");
 * const result = await client.query("SELECT * FROM users WHERE age > $1", [30]);
 * console.log(result.rows);
 * ```
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ClientOptions {
  apiKey?: string;
  timeout?: number;
}

export interface QueryResultData {
  rows: Record<string, unknown>[];
  rowCount: number;
  fields?: Array<{ name: string }>;
  [key: string]: unknown;
}

export interface HealthResponse {
  status: string;
  [key: string]: unknown;
}

export interface CreateTaskOptions {
  agentId: string;
  instruction: string;
  priority?: number;
  metadata?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

export class CortexDBError extends Error {
  public readonly statusCode: number | undefined;
  public readonly responseBody: unknown;

  constructor(
    message: string,
    statusCode?: number,
    responseBody?: unknown,
  ) {
    super(message);
    this.name = "CortexDBError";
    this.statusCode = statusCode;
    this.responseBody = responseBody;
  }
}

export class ConnectionError extends CortexDBError {
  constructor(message: string) {
    super(message);
    this.name = "ConnectionError";
  }
}

export class AuthenticationError extends CortexDBError {
  constructor(message: string, statusCode?: number, responseBody?: unknown) {
    super(message, statusCode, responseBody);
    this.name = "AuthenticationError";
  }
}

export class QueryError extends CortexDBError {
  constructor(message: string, statusCode?: number, responseBody?: unknown) {
    super(message, statusCode, responseBody);
    this.name = "QueryError";
  }
}

// ---------------------------------------------------------------------------
// QueryResult
// ---------------------------------------------------------------------------

export class QueryResult {
  private readonly _raw: QueryResultData;

  constructor(raw: Record<string, unknown>) {
    this._raw = raw as QueryResultData;
  }

  get rows(): Record<string, unknown>[] {
    return (
      this._raw.rows ??
      (this._raw as Record<string, unknown>).data as Record<string, unknown>[] ??
      []
    );
  }

  get rowCount(): number {
    return this._raw.rowCount ?? this.rows.length;
  }

  get columns(): string[] {
    const fields = this._raw.fields;
    if (!fields) return [];
    return fields.map((f) => f.name);
  }

  get raw(): QueryResultData {
    return this._raw;
  }

  [Symbol.iterator](): Iterator<Record<string, unknown>> {
    return this.rows[Symbol.iterator]();
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildHeaders(apiKey?: string, token?: string): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };
  if (apiKey) headers["X-API-Key"] = apiKey;
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return headers;
}

async function safeJson(resp: Response): Promise<Record<string, unknown>> {
  try {
    return (await resp.json()) as Record<string, unknown>;
  } catch {
    return { text: await resp.text() };
  }
}

async function handleResponse(resp: Response): Promise<Record<string, unknown>> {
  if (resp.status === 401 || resp.status === 403) {
    const body = await safeJson(resp);
    throw new AuthenticationError(
      `Authentication failed (${resp.status})`,
      resp.status,
      body,
    );
  }
  if (resp.status >= 400) {
    const body = await safeJson(resp);
    const msg =
      (body as Record<string, unknown>).error ??
      (body as Record<string, unknown>).message ??
      JSON.stringify(body);
    throw new QueryError(
      `Request failed (${resp.status}): ${msg}`,
      resp.status,
      body,
    );
  }
  return safeJson(resp);
}

// ---------------------------------------------------------------------------
// CortexDBClient
// ---------------------------------------------------------------------------

/**
 * Lightweight client for CortexDB query and write operations.
 *
 * Uses the native `fetch` API — no external dependencies required.
 */
export class CortexDBClient {
  public readonly baseUrl: string;
  private readonly apiKey?: string;
  private readonly timeout: number;
  private _abortController: AbortController | null = null;

  /**
   * @param baseUrl - Root URL of the CortexDB instance (e.g. `http://localhost:5400`).
   * @param options - Optional API key and timeout.
   */
  constructor(baseUrl: string, options: ClientOptions = {}) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.apiKey = options.apiKey;
    this.timeout = options.timeout ?? 30_000;
  }

  /** Close any pending requests. */
  close(): void {
    this._abortController?.abort();
    this._abortController = null;
  }

  // -- Internal fetch wrapper ----------------------------------------------

  private async _fetch(
    path: string,
    init: RequestInit = {},
  ): Promise<Record<string, unknown>> {
    this._abortController = new AbortController();
    const timer = setTimeout(() => this._abortController?.abort(), this.timeout);

    try {
      const resp = await fetch(`${this.baseUrl}${path}`, {
        ...init,
        headers: {
          ...buildHeaders(this.apiKey),
          ...(init.headers as Record<string, string> | undefined),
        },
        signal: this._abortController.signal,
      });
      return await handleResponse(resp);
    } catch (err) {
      if (err instanceof CortexDBError) throw err;
      throw new ConnectionError(
        `Cannot connect to ${this.baseUrl}: ${(err as Error).message}`,
      );
    } finally {
      clearTimeout(timer);
    }
  }

  // -- Core operations -----------------------------------------------------

  /**
   * Execute a read query against CortexDB.
   *
   * @param cortexql - The CortexQL / SQL statement.
   * @param params - Bind parameters for the query.
   */
  async query(
    cortexql: string,
    params?: Record<string, unknown> | unknown[],
  ): Promise<QueryResult> {
    const payload: Record<string, unknown> = { cortexql };
    if (params !== undefined) payload.params = params;

    const data = await this._fetch("/v1/query", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return new QueryResult(data);
  }

  /**
   * Execute a write operation (INSERT / UPDATE / DELETE) against CortexDB.
   *
   * @param cortexql - The CortexQL / SQL statement.
   * @param params - Bind parameters.
   */
  async write(
    cortexql: string,
    params?: Record<string, unknown> | unknown[],
  ): Promise<QueryResult> {
    const payload: Record<string, unknown> = { cortexql };
    if (params !== undefined) payload.params = params;

    const data = await this._fetch("/v1/write", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return new QueryResult(data);
  }

  // -- Health --------------------------------------------------------------

  /** Basic readiness check (`GET /health/ready`). */
  async health(): Promise<HealthResponse> {
    return (await this._fetch("/health/ready")) as HealthResponse;
  }

  /** Deep health check covering all internal engines (`GET /health/deep`). */
  async deepHealth(): Promise<HealthResponse> {
    return (await this._fetch("/health/deep")) as HealthResponse;
  }
}

// ---------------------------------------------------------------------------
// SuperAdminClient
// ---------------------------------------------------------------------------

/**
 * Client for CortexDB SuperAdmin / management operations.
 *
 * Wraps the gateway API for agent management, task control, chat,
 * and marketplace access.
 */
export class SuperAdminClient {
  public readonly baseUrl: string;
  private readonly apiKey?: string;
  private readonly timeout: number;
  private _token: string | null = null;

  constructor(baseUrl: string, options: ClientOptions = {}) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.apiKey = options.apiKey;
    this.timeout = options.timeout ?? 30_000;
  }

  /** Whether the client has an active auth token. */
  get isAuthenticated(): boolean {
    return this._token !== null;
  }

  close(): void {
    this._token = null;
  }

  // -- Internal helpers ----------------------------------------------------

  private async _fetch(
    path: string,
    init: RequestInit = {},
  ): Promise<Record<string, unknown>> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeout);

    try {
      const resp = await fetch(`${this.baseUrl}${path}`, {
        ...init,
        headers: {
          ...buildHeaders(this.apiKey, this._token ?? undefined),
          ...(init.headers as Record<string, string> | undefined),
        },
        signal: controller.signal,
      });
      return await handleResponse(resp);
    } catch (err) {
      if (err instanceof CortexDBError) throw err;
      throw new ConnectionError(
        `Cannot connect to ${this.baseUrl}: ${(err as Error).message}`,
      );
    } finally {
      clearTimeout(timer);
    }
  }

  private async _get(
    path: string,
    params?: Record<string, string>,
  ): Promise<Record<string, unknown>> {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return this._fetch(`${path}${qs}`);
  }

  private async _post(
    path: string,
    body?: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    return this._fetch(path, {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    });
  }

  // -- Authentication ------------------------------------------------------

  /**
   * Authenticate with the superadmin passphrase.
   * The JWT token is stored and sent with all subsequent requests.
   */
  async login(passphrase: string): Promise<Record<string, unknown>> {
    const data = await this._post("/api/v1/auth/login", { passphrase });
    const token = (data.token ?? data.access_token) as string | undefined;
    if (!token) {
      throw new AuthenticationError(
        "Login response did not contain a token",
        undefined,
        data,
      );
    }
    this._token = token;
    return data;
  }

  // -- Agents --------------------------------------------------------------

  /**
   * List all agents, optionally filtered.
   * @param filters - Query-string filters (e.g. `{ department: "operations" }`).
   */
  async listAgents(
    filters?: Record<string, string>,
  ): Promise<Record<string, unknown>[]> {
    const data = await this._get("/api/v1/agents", filters);
    if (Array.isArray(data)) return data as Record<string, unknown>[];
    return (
      (data.agents as Record<string, unknown>[]) ??
      (data.data as Record<string, unknown>[]) ??
      []
    );
  }

  /** Get a single agent by ID. */
  async getAgent(agentId: string): Promise<Record<string, unknown>> {
    return this._get(`/api/v1/agents/${agentId}`);
  }

  // -- Tasks ---------------------------------------------------------------

  /** Create and assign a task to an agent. */
  async createTask(options: CreateTaskOptions): Promise<Record<string, unknown>> {
    return this._post("/api/v1/tasks", {
      agent_id: options.agentId,
      instruction: options.instruction,
      priority: options.priority ?? 5,
      ...(options.metadata ? { metadata: options.metadata } : {}),
    });
  }

  /** List tasks, optionally filtered. */
  async listTasks(
    filters?: Record<string, string>,
  ): Promise<Record<string, unknown>[]> {
    const data = await this._get("/api/v1/tasks", filters);
    if (Array.isArray(data)) return data as Record<string, unknown>[];
    return (
      (data.tasks as Record<string, unknown>[]) ??
      (data.data as Record<string, unknown>[]) ??
      []
    );
  }

  // -- Chat ----------------------------------------------------------------

  /** Send a chat message to an agent and get a response. */
  async chat(
    agentId: string,
    message: string,
  ): Promise<Record<string, unknown>> {
    return this._post("/api/v1/agents/chat", {
      agent_id: agentId,
      message,
    });
  }

  // -- Marketplace ---------------------------------------------------------

  /** List all marketplace templates / integrations. */
  async marketplaceList(): Promise<Record<string, unknown>[]> {
    const data = await this._get("/api/v1/marketplace");
    if (Array.isArray(data)) return data as Record<string, unknown>[];
    return (
      (data.items as Record<string, unknown>[]) ??
      (data.templates as Record<string, unknown>[]) ??
      (data.data as Record<string, unknown>[]) ??
      []
    );
  }

  /** Enable / activate a marketplace item. */
  async marketplaceEnable(
    itemId: string,
  ): Promise<Record<string, unknown>> {
    return this._post(`/api/v1/marketplace/${itemId}/enable`);
  }

  /** Disable / deactivate a marketplace item. */
  async marketplaceDisable(
    itemId: string,
  ): Promise<Record<string, unknown>> {
    return this._post(`/api/v1/marketplace/${itemId}/disable`);
  }
}
