import React, { useState } from 'react';
import type { Citation } from '../types';

interface CitationCardProps {
  citation: Citation;
  index: number;
}

export const CitationCard: React.FC<CitationCardProps> = ({ citation, index }) => {
  const [expanded, setExpanded] = useState(false);

  const fileName = citation.file_path.split('/').pop() || citation.file_path;

  return (
    <div className="ad-citation">
      <div
        className="ad-citation-header"
        onClick={() => setExpanded(!expanded)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') setExpanded(!expanded);
        }}
      >
        <span>
          <span className="ad-citation-file">[Source {index + 1}]</span>{' '}
          {fileName}
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="ad-citation-score">
            score: {citation.score.toFixed(3)}
          </span>
          <span className="ad-citation-toggle">{expanded ? '▲' : '▼'}</span>
        </span>
      </div>
      {expanded && (
        <div className="ad-citation-snippet">{citation.snippet}</div>
      )}
    </div>
  );
};
