export type Role = "participant" | "staff" | "organizer" | "admin";

export interface User { id: string; name: string; email: string; role: Role; course?: string | null; managed_event_ids?: string[] | null }

export interface Room { id: string; name: string; building: string; capacity: number; resources: string[]; available: boolean }
export interface Speaker { id: string; name: string; affiliation: string; bio: string }
export interface Session {
  id: string; event_id: string; code: string; title: string; description: string; kind: string; track: string;
  start_at: string; end_at: string; max_capacity: number; available_spots: number; workload_hours: number; status: string;
  room: Room | null; speakers: Speaker[];
}
export interface EventSummary {
  id: string; slug: string; title: string; description: string; category: string; modality: string; location: string;
  start_at: string; end_at: string; status: string; cover_url: string | null; max_minicursos_per_participant: number;
  sessions_count: number; total_capacity: number; total_registered: number;
}
export interface EventDetail extends Omit<EventSummary, "sessions_count" | "total_capacity" | "total_registered"> {
  sessions: Session[]; rooms: Room[]; speakers: Speaker[];
}
export interface Ticket {
  id: string; ticket_code: string; user_id: string; event_id: string; session_id: string; status: "CONFIRMED" | "CHECKED_IN" | "CANCELLED";
  checked_in_at: string | null; cancelled_at: string | null; cancel_reason: string | null; created_at: string; session: Session | null;
}
export interface Attendee extends Ticket { participant_name: string; participant_email: string }

export interface Proposal {
  id: string; run_id: string | null; kind: "CANCEL_TICKET" | "SWAP_SESSION" | "ACTION_PLAN"; level: "L2" | "L3"; event_id: string | null;
  requested_by: string; title: string; summary: string; payload: any; impact: any; communication: { title: string; body: string } | null;
  review: any; status: "PENDING" | "APPROVED" | "REJECTED" | "EXECUTED" | "FAILED"; decided_by: string | null; decided_at: string | null;
  decision_note: string | null; executed_at: string | null; result: any; error: string | null; created_at: string;
}
export interface ProposalCard { id: string; kind: Proposal["kind"]; level: string; title: string; summary: string; status: Proposal["status"]; impact: any }

export interface Evidence { source_id: string; section: string; title?: string; trust?: string }
export interface ChatResult {
  run_id: string; conversation_id: string; status: string; answer: string; kind: string; evidence: Evidence[];
  proposals: ProposalCard[]; support_requests: string[]; budget: any; reason: string | null;
}
export interface Step {
  run_id?: string; seq: number; type: string; name: string; agent: string | null; status: string; input: any; output: any;
  duration_ms: number | null; tokens_in: number | null; tokens_out: number | null; created_at?: string; at?: string;
}
export interface Run {
  id: string; agent: string; user_id: string | null; event_id: string | null; conversation_id: string | null; correlation_id: string | null;
  status: string; current_node: string | null; input: string; model_calls: number; tool_calls: number; tokens_in: number; tokens_out: number;
  started_at: string; ended_at: string | null; error: string | null;
}
export interface RunDetail extends Run { state: any; output: any; steps: Step[] }

export interface Notification { id: string; title: string; body: string; link: string | null; read_at: string | null; created_at: string }
export interface SupportRequest { id: string; user_id: string; event_id: string | null; summary: string; status: string; answer: string | null; run_id: string | null; created_at: string }
export interface Activity {
  id: string; occurred_at: string; entity_type: string; entity_id: string; action: string; level: string; source: string;
  actor_id: string | null; actor_role: string | null; correlation_id: string | null; message: string; payload: any; status: string; notes: string | null;
}
export interface KnowledgeDoc { id: string; source_id: string; title: string; source_path: string; version: number; status: string; trust: string; updated_at: string; sections: number }
