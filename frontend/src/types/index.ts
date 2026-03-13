export interface Citation {
  doc_id: string;
  chunk_id: string;
  file_path: string;
  score: number;
  snippet: string;
}

export interface TokenEvent {
  text: string;
}

export interface DoneEvent {
  token_count: number;
  abstained?: boolean;
}

export interface ErrorEvent {
  error: string;
}

export type SSEEventType = 'token' | 'citation' | 'done' | 'error';

export interface AskDocsWidgetProps {
  /** Backend API base URL. Defaults to '' (same origin). */
  apiBaseUrl?: string;
  /** Placeholder text for the input field */
  placeholder?: string;
  /** Maximum number of sources to retrieve */
  topK?: number;
  /** Title shown at the top of the widget */
  title?: string;
}
