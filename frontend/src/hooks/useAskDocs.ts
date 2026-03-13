import { useState, useCallback, useRef } from 'react';
import type { Citation, TokenEvent, DoneEvent, ErrorEvent } from '../types';

interface UseAskDocsReturn {
  answer: string;
  citations: Citation[];
  isStreaming: boolean;
  tokenCount: number;
  abstained: boolean;
  error: string | null;
  modelError: string | null;
  retrievalError: string | null;
  ask: (question: string, topK?: number) => void;
  reset: () => void;
}

export function useAskDocs(apiBaseUrl = ''): UseAskDocsReturn {
  const [answer, setAnswer] = useState('');
  const [citations, setCitations] = useState<Citation[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [tokenCount, setTokenCount] = useState(0);
  const [abstained, setAbstained] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modelError, setModelError] = useState<string | null>(null);
  const [retrievalError, setRetrievalError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setAnswer('');
    setCitations([]);
    setIsStreaming(false);
    setTokenCount(0);
    setAbstained(false);
    setError(null);
    setModelError(null);
    setRetrievalError(null);
  }, []);

  const ask = useCallback(
    (question: string, topK = 5) => {
      reset();
      setIsStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      fetch(`${apiBaseUrl}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, top_k: topK }),
        signal: controller.signal,
      })
        .then(async (response) => {
          if (!response.ok) {
            const body = await response.text();
            if (response.status === 429) {
              setRetrievalError('Rate limit exceeded. Please wait and try again.');
            } else {
              setRetrievalError(`Request failed (${response.status}): ${body}`);
            }
            setIsStreaming(false);
            return;
          }

          const reader = response.body?.getReader();
          if (!reader) {
            setError('No response stream');
            setIsStreaming(false);
            return;
          }

          const decoder = new TextDecoder();
          let buffer = '';

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            let currentEvent = '';
            for (const line of lines) {
              if (line.startsWith('event: ')) {
                currentEvent = line.slice(7).trim();
              } else if (line.startsWith('data: ')) {
                const data = line.slice(6);
                try {
                  const parsed = JSON.parse(data);
                  switch (currentEvent) {
                    case 'token': {
                      const tokenData = parsed as TokenEvent;
                      setAnswer((prev) => prev + tokenData.text);
                      break;
                    }
                    case 'citation': {
                      const cit = parsed as Citation;
                      setCitations((prev) => [...prev, cit]);
                      break;
                    }
                    case 'done': {
                      const doneData = parsed as DoneEvent;
                      setTokenCount(doneData.token_count);
                      if (doneData.abstained) setAbstained(true);
                      break;
                    }
                    case 'error': {
                      const errData = parsed as ErrorEvent;
                      setModelError(errData.error);
                      break;
                    }
                  }
                } catch {
                  // skip malformed JSON lines
                }
              }
            }
          }
          setIsStreaming(false);
        })
        .catch((err: Error) => {
          if (err.name !== 'AbortError') {
            setError(err.message);
          }
          setIsStreaming(false);
        });
    },
    [apiBaseUrl, reset],
  );

  return {
    answer,
    citations,
    isStreaming,
    tokenCount,
    abstained,
    error,
    modelError,
    retrievalError,
    ask,
    reset,
  };
}
