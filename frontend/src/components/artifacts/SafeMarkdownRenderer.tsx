import React from 'react';

interface SafeMarkdownRendererProps {
  content: string;
}

/**
 * Renders Markdown safely without dangerouslySetInnerHTML.
 * Treats all raw HTML as untrusted text, escaping all tags.
 * Supports headings, tables, blockquotes, lists, code blocks, bold, italics, and safe links.
 */
export const SafeMarkdownRenderer: React.FC<SafeMarkdownRendererProps> = ({ content }) => {
  // Parse inline elements (bold, italic, code, safe link)
  const renderInline = (text: string): React.ReactNode[] => {
    const nodes: React.ReactNode[] = [];
    // Tokenize inline markdown
    // Regex matches inline code `code`, bold **text**, italic *text*, links [text](url)
    const regex = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g;
    let lastIndex = 0;
    let match: RegExpExecArray | null;

    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        nodes.push(text.substring(lastIndex, match.index));
      }

      const token = match[0];
      if (token.startsWith('`') && token.endsWith('`')) {
        nodes.push(
          <code key={match.index} className="inline-code">
            {token.slice(1, -1)}
          </code>
        );
      } else if (token.startsWith('**') && token.endsWith('**')) {
        nodes.push(
          <strong key={match.index}>
            {token.slice(2, -2)}
          </strong>
        );
      } else if (token.startsWith('*') && token.endsWith('*')) {
        nodes.push(
          <em key={match.index}>
            {token.slice(1, -1)}
          </em>
        );
      } else if (token.startsWith('[') && token.includes('](')) {
        const linkMatch = token.match(/\[([^\]]+)\]\(([^)]+)\)/);
        if (linkMatch) {
          const linkText = linkMatch[1];
          const rawUrl = linkMatch[2].trim();
          // Security: only allow safe http/https links
          const isSafeUrl = /^https?:\/\//i.test(rawUrl);
          if (isSafeUrl) {
            nodes.push(
              <a
                key={match.index}
                href={rawUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="safe-markdown-link"
              >
                {linkText}
              </a>
            );
          } else {
            nodes.push(`${linkText} (${rawUrl})`);
          }
        }
      }

      lastIndex = match.index + token.length;
    }

    if (lastIndex < text.length) {
      nodes.push(text.substring(lastIndex));
    }

    return nodes.length > 0 ? nodes : [text];
  };

  // Block parser
  const renderBlocks = () => {
    const lines = content.split('\n');
    const elements: React.ReactNode[] = [];
    let i = 0;

    while (i < lines.length) {
      const line = lines[i];
      const trimmed = line.trim();

      // Empty line
      if (!trimmed) {
        i++;
        continue;
      }

      // Code block
      if (trimmed.startsWith('```')) {
        const lang = trimmed.slice(3).trim();
        const codeLines: string[] = [];
        i++;
        while (i < lines.length && !lines[i].trim().startsWith('```')) {
          codeLines.push(lines[i]);
          i++;
        }
        i++; // skip closing ```
        elements.push(
          <div key={`code-${i}`} className="markdown-code-block-container">
            {lang && <span className="code-lang-tag">{lang}</span>}
            <pre className="markdown-code-block">
              <code>{codeLines.join('\n')}</code>
            </pre>
          </div>
        );
        continue;
      }

      // Markdown Table
      if (trimmed.startsWith('|') && trimmed.endsWith('|') && i + 1 < lines.length && lines[i + 1].includes('---')) {
        const headerCols = trimmed.split('|').filter((c) => c !== '').map((c) => c.trim());
        i += 2; // skip header and separator
        const rows: string[][] = [];
        while (i < lines.length && lines[i].trim().startsWith('|') && lines[i].trim().endsWith('|')) {
          const rowCols = lines[i].trim().split('|').filter((c) => c !== '').map((c) => c.trim());
          rows.push(rowCols);
          i++;
        }
        elements.push(
          <div key={`table-${i}`} className="markdown-table-wrapper">
            <table className="markdown-table">
              <thead>
                <tr>
                  {headerCols.map((col, cIdx) => (
                    <th key={cIdx}>{renderInline(col)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, rIdx) => (
                  <tr key={rIdx}>
                    {r.map((col, cIdx) => (
                      <td key={cIdx}>{renderInline(col)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
        continue;
      }

      // Headings
      if (trimmed.startsWith('# ')) {
        elements.push(<h1 key={`h1-${i}`} className="markdown-h1">{renderInline(trimmed.slice(2))}</h1>);
        i++;
        continue;
      }
      if (trimmed.startsWith('## ')) {
        elements.push(<h2 key={`h2-${i}`} className="markdown-h2">{renderInline(trimmed.slice(3))}</h2>);
        i++;
        continue;
      }
      if (trimmed.startsWith('### ')) {
        elements.push(<h3 key={`h3-${i}`} className="markdown-h3">{renderInline(trimmed.slice(4))}</h3>);
        i++;
        continue;
      }
      if (trimmed.startsWith('#### ')) {
        elements.push(<h4 key={`h4-${i}`} className="markdown-h4">{renderInline(trimmed.slice(5))}</h4>);
        i++;
        continue;
      }

      // Blockquote
      if (trimmed.startsWith('> ')) {
        const quoteLines: string[] = [trimmed.slice(2)];
        i++;
        while (i < lines.length && lines[i].trim().startsWith('> ')) {
          quoteLines.push(lines[i].trim().slice(2));
          i++;
        }
        elements.push(
          <blockquote key={`quote-${i}`} className="markdown-blockquote">
            {renderInline(quoteLines.join(' '))}
          </blockquote>
        );
        continue;
      }

      // Bullet list
      if (trimmed.startsWith('* ') || trimmed.startsWith('- ')) {
        const listItems: string[] = [trimmed.slice(2)];
        i++;
        while (i < lines.length && (lines[i].trim().startsWith('* ') || lines[i].trim().startsWith('- '))) {
          listItems.push(lines[i].trim().slice(2));
          i++;
        }
        elements.push(
          <ul key={`ul-${i}`} className="markdown-ul">
            {listItems.map((item, lIdx) => (
              <li key={lIdx}>{renderInline(item)}</li>
            ))}
          </ul>
        );
        continue;
      }

      // Numbered list
      if (/^\d+\.\s/.test(trimmed)) {
        const listItems: string[] = [trimmed.replace(/^\d+\.\s/, '')];
        i++;
        while (i < lines.length && /^\d+\.\s/.test(lines[i].trim())) {
          listItems.push(lines[i].trim().replace(/^\d+\.\s/, ''));
          i++;
        }
        elements.push(
          <ol key={`ol-${i}`} className="markdown-ol">
            {listItems.map((item, lIdx) => (
              <li key={lIdx}>{renderInline(item)}</li>
            ))}
          </ol>
        );
        continue;
      }

      // Standard paragraph
      elements.push(
        <p key={`p-${i}`} className="markdown-p">
          {renderInline(trimmed)}
        </p>
      );
      i++;
    }

    return elements;
  };

  return <div className="safe-markdown-article">{renderBlocks()}</div>;
};
