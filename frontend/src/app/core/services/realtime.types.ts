/**
 * Shared types for the RealtimeService + consumers of its streams.
 *
 * Phase R0 of the approved plan. The backend consumer lives at
 * backend/apps/realtime/consumers.py. Keep shapes in sync with its docstring.
 */

/** WebSocket connection lifecycle state. Consumed by Gap 38 status dot. */
export type ConnectionStatus = 'connected' | 'reconnecting' | 'offline';

/** A message that originated from a backend broadcast on a topic. */
export interface TopicUpdate<TPayload = unknown> {
  /** Topic name as sent by the producer (not sanitized). */
  topic: string;
  /** Short event name within the topic, e.g. 'entity.updated'. */
  event: string;
  /** JSON payload chosen by the producer. Shape varies by topic. */
  payload: TPayload;
  /** Client-side receipt timestamp (ms since epoch). */
  receivedAt: number;
}

/** Client → server frames. */
export interface SubscribeFrame {
  action: 'subscribe';
  topics: string[];
}
export interface UnsubscribeFrame {
  action: 'unsubscribe';
  topics: string[];
}
export interface PingFrame {
  action: 'ping';
}
/** Phase RC / Gaps 139-142 — client-originated broadcast on a
 *  collaboration topic (presence / cursor / lock / typing). */
export interface PublishFrame {
  action: 'publish';
  topic: string;
  event: string;
  payload: Record<string, unknown>;
}
export type OutgoingFrame =
  | SubscribeFrame
  | UnsubscribeFrame
  | PingFrame
  | PublishFrame;

/** Server → client frames. */
export interface ConnectionEstablishedFrame {
  type: 'connection.established';
  message: string;
}
export interface SubscriptionAckFrame {
  type: 'subscription.ack';
  topics: string[];
  denied: string[];
}
export interface UnsubscriptionAckFrame {
  type: 'unsubscription.ack';
  topics: string[];
}
export interface PongFrame {
  type: 'pong';
}
export interface TopicUpdateFrame {
  type: 'topic.update';
  topic: string;
  event: string;
  payload: unknown;
}
export interface ErrorFrame {
  type: 'error';
  message: string;
}
export type IncomingFrame =
  | ConnectionEstablishedFrame
  | SubscriptionAckFrame
  | UnsubscriptionAckFrame
  | PongFrame
  | TopicUpdateFrame
  | ErrorFrame;
