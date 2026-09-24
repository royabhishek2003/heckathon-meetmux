/**
 * API client – all backend communication goes through here.
 * Uses the Vite proxy in dev (/api → localhost:8000).
 */

import type {
  HealthResponse,
  RoutePlanRequest,
  RoutePlanResponse,
  ShipmentDetail,
  ShipmentListResponse,
  ShipmentNetworkResponse,
} from '../types';

const envBase = (import.meta.env.VITE_API_BASE_URL || '').trim();
const API_BASE = envBase
  ? (envBase.startsWith('http://') || envBase.startsWith('https://') ? envBase : `https://${envBase}`).replace(/\/+$/, '')
  : '';

class ApiError extends Error {
  status: number;
  requestId?: string;

  constructor(message: string, status: number, requestId?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.requestId = requestId;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}/api/v1${path}`;

  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new ApiError(
        body.message || body.detail || `Request failed (${response.status})`,
        response.status,
        body.request_id
      );
    }

    return response.json();
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(
      'Unable to reach the server. Please check your connection.',
      0
    );
  }
}

// ── Health ──────────────────────────────────────────────

export async function getHealth(): Promise<HealthResponse> {
  return request('/health');
}

// ── Shipments ───────────────────────────────────────────

export async function getShipments(
  page = 1,
  pageSize = 20,
  status?: string
): Promise<ShipmentListResponse> {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (status) params.set('status', status);
  return request(`/shipments?${params}`);
}

export async function getShipment(id: string): Promise<ShipmentDetail> {
  return request(`/shipments/${encodeURIComponent(id)}`);
}

export async function getShipmentNetwork(id: string): Promise<ShipmentNetworkResponse> {
  return request(`/shipments/${encodeURIComponent(id)}/network`);
}

// ── Routes ──────────────────────────────────────────────

export async function planRoutes(req: RoutePlanRequest): Promise<RoutePlanResponse> {
  return request('/routes/plan', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export { ApiError };
