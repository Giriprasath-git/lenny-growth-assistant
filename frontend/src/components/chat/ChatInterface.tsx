import React from 'react';
import { ChatMessage, Citation } from '../../types/chat';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';

interface ChatInterfaceProps {
  messages: ChatMessage[];
  onSendMessage: (text: string) => void;
  onSelectCitation: (citation: Citation) => void;
  activeCitation?: Citation | null;
  isLoading: boolean;
  loadingStatusText?: string;
  ship30Active: boolean;
  onToggleShip30: () => void;
  isPiSdkMode?: boolean;
  onSelectSampleQuestion?: (question: string) => void;
  error?: string | null;
  onRetry?: () => void;
  onCreateArtifact?: (msg: ChatMessage) => void;
}

export const ChatInterface: React.FC<ChatInterfaceProps> = ({
  messages,
  onSendMessage,
  onSelectCitation,
  activeCitation,
  isLoading,
  loadingStatusText,
  ship30Active,
  onToggleShip30,
  isPiSdkMode = false,
  onSelectSampleQuestion,
  error = null,
  onRetry,
  onCreateArtifact,
}) => {
  return (
    <div className="chat-container">
      <MessageList
        messages={messages}
        onSelectCitation={onSelectCitation}
        activeCitation={activeCitation}
        isLoading={isLoading}
        loadingStatusText={loadingStatusText}
        onSelectSampleQuestion={onSelectSampleQuestion}
        error={error}
        onRetry={onRetry}
        onCreateArtifact={onCreateArtifact}
      />
      <MessageInput
        onSendMessage={onSendMessage}
        disabled={isLoading}
        ship30Active={ship30Active}
        onToggleShip30={onToggleShip30}
        isPiSdkMode={isPiSdkMode}
      />
    </div>
  );
};
