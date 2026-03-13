import React, { useState, useCallback } from 'react';
import { useAskDocs } from '../hooks/useAskDocs';
import { CitationCard } from './CitationCard';
import type { AskDocsWidgetProps } from '../types';
import '../styles/widget.css';

export const AskDocsWidget: React.FC<AskDocsWidgetProps> = ({
  apiBaseUrl = '',
  placeholder = 'Ask a question about the docs…',
  topK = 5,
  title = 'Ask Docs',
}) => {
  const [question, setQuestion] = useState('');
  const {
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
  } = useAskDocs(apiBaseUrl);

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      if (question.trim() && !isStreaming) {
        ask(question.trim(), topK);
      }
    },
    [question, isStreaming, ask, topK],
  );

  const handleReset = useCallback(() => {
    setQuestion('');
    reset();
  }, [reset]);

  const hasContent = answer || citations.length > 0 || error || modelError || retrievalError;

  return (
    <div className="ask-docs-widget">
      {/* Header */}
      <div className="ad-header">
        <h3 className="ad-title">{title}</h3>
        {tokenCount > 0 && (
          <span className="ad-token-badge">~{tokenCount} tokens</span>
        )}
      </div>

      {/* Input */}
      <form className="ad-input-row" onSubmit={handleSubmit}>
        <input
          className="ad-input"
          type="text"
          placeholder={placeholder}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={isStreaming}
        />
        <button className="ad-btn" type="submit" disabled={isStreaming || !question.trim()}>
          {isStreaming ? 'Thinking…' : 'Ask'}
        </button>
        {hasContent && (
          <button className="ad-btn" type="button" onClick={handleReset} style={{ background: '#64748b' }}>
            Clear
          </button>
        )}
      </form>

      {/* Errors — separated model vs retrieval */}
      {error && (
        <div className="ad-error ad-error--general">⚠ {error}</div>
      )}
      {modelError && (
        <div className="ad-error ad-error--model">Model error: {modelError}</div>
      )}
      {retrievalError && (
        <div className="ad-error ad-error--retrieval">Retrieval error: {retrievalError}</div>
      )}

      {/* Abstention badge */}
      {abstained && (
        <span className="ad-abstain-badge">Low confidence — answer may be incomplete</span>
      )}

      {/* Answer */}
      {(answer || isStreaming) && (
        <div className="ad-answer-box">
          {answer}
          {isStreaming && <span className="ad-cursor" />}
        </div>
      )}

      {/* Citations */}
      {citations.length > 0 && (
        <div className="ad-citations">
          <div className="ad-citations-title">
            Sources ({citations.length})
          </div>
          {citations.map((cit, i) => (
            <CitationCard key={cit.chunk_id} citation={cit} index={i} />
          ))}
        </div>
      )}
    </div>
  );
};
