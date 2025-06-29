"use client";

import React, { useRef, useEffect } from 'react';
import { useSession, signOut, signIn } from 'next-auth/react';
import { LogIn, LogOut } from 'lucide-react';
import { Message } from '@/types';
import { ScrollArea } from '@/components/ui/scroll-area';
import { MessageList } from '@/components/chat/MessageList';

interface ChatPanelProps {
  currentMessages: Message[];
  isFetchingMessages: boolean;
  isLoading: boolean;
  isGenerating: boolean;
  inputValue: string;
  setInputValue: (value: string) => void;
  handleSendMessage: () => void;
  handleStopGeneration: () => void;
  interactionDisabled: boolean;
  activeChatId: string | null;
  activeTypingMessageId: string | null;
  currentThought?: string | null;
  selectedModel: string;
  setSelectedModel: React.Dispatch<React.SetStateAction<string>>;
  handleRerunMessage: (userMsgId: string, text: string) => void;
  handleDeleteUserPair: (userMsgId: string) => void;
  availableModels: string[];
  notebookTitle: string;
  onRenameNotebook: (newTitle: string) => void;
  runningUserMessageId: string | null;
}

function ChatHeader({ title, onRename }: { title: string; onRename: (t: string) => void }) {
  const { data: session } = useSession();
  const [isEditing, setIsEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(title);

  // Keep local draft in sync when title changes externally
  React.useEffect(() => {
    if (!isEditing) {
      setDraft(title);
    }
  }, [title, isEditing]);

  const confirm = () => {
    setIsEditing(false);
    const trimmed = draft.trim();
    if (trimmed && trimmed !== title) {
      onRename(trimmed);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      confirm();
    } else if (e.key === "Escape") {
      setIsEditing(false);
      setDraft(title);
    }
  };

  return (
    <div className="bg-chatgpt-hover h-12 flex items-center justify-between px-4 flex-shrink-0 border-b border-chatgpt">
      {/* Title & edit button */}
      <div className="flex items-center gap-2 max-w-full">
        {isEditing ? (
          <input
            className="bg-transparent border-b border-chatgpt-accent focus:outline-none text-chatgpt text-sm truncate max-w-xs"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={confirm}
            onKeyDown={handleKeyDown}
            autoFocus
          />
        ) : (
          <span className="text-chatgpt font-medium truncate max-w-xs">{title}</span>
        )}
        {!isEditing && (
          <button
            onClick={() => setIsEditing(true)}
            className="text-chatgpt hover:text-chatgpt-accent cursor-pointer"
            title="Edit title"
          >
            {/* Pencil icon */}
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-4 w-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 20h9" />
              <path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4 12.5-12.5z" />
            </svg>
          </button>
        )}
      </div>
      {/* Sign out button */}
      {session?.user && (
        <div className="relative group">
          <button
            onClick={() => signOut()}
            className="w-7 h-7 bg-chatgpt-accent rounded-full flex items-center justify-center text-sm font-medium text-white hover:opacity-80 transition-opacity cursor-pointer"
            title={`${session.user.name ?? session.user.email} - Click to sign out`}
          >
            {/* User initial - visible by default, hidden on hover */}
            <span className="group-hover:opacity-0 transition-opacity duration-200">
              {session.user.name?.charAt(0) || session.user.email?.charAt(0) || 'U'}
            </span>
            {/* Logout icon - hidden by default, visible on hover */}
            <LogOut className="w-4 h-4 absolute opacity-0 group-hover:opacity-100 transition-opacity duration-200" />
          </button>
        </div>
      )}
    </div>
  );
}

export function ChatPanel({
  currentMessages,
  isFetchingMessages,
  isLoading,
  isGenerating,
  inputValue,
  setInputValue,
  handleSendMessage,
  handleStopGeneration,
  interactionDisabled,
  activeChatId,
  activeTypingMessageId,
  currentThought,
  selectedModel,
  setSelectedModel,
  handleRerunMessage,
  handleDeleteUserPair,
  availableModels,
  notebookTitle,
  onRenameNotebook,
  runningUserMessageId,
}: ChatPanelProps) {
  const { data: session, status } = useSession();
  const lastMessageRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll when a new USER message is added so that it stays visible near the bottom.
  useEffect(() => {
    if (!currentMessages.length) return;

    const last = currentMessages[currentMessages.length - 1];

    if (last.sender === 'user' && lastMessageRef.current) {
      // Scroll so that the user bubble is near the bottom edge but still visible.
      lastMessageRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [currentMessages]);

  if (status !== 'loading' && !session?.user) {
    return (
      <main className="flex-1 flex flex-col overflow-hidden bg-chatgpt-hover">
        <ChatHeader title={notebookTitle} onRename={onRenameNotebook} />
        <div className="flex-1 flex items-center justify-center -mt-20">
          <button
            onClick={() => signIn('google', { callbackUrl: '/' })}
            className="bg-chatgpt-sidebar hover:bg-chatgpt-hover transition-colors text-chatgpt font-medium flex items-center gap-2 px-6 py-3 rounded-lg cursor-pointer"
          >
            <LogIn className="w-5 h-5" />
            <span>Login</span>
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="flex-1 flex flex-col overflow-hidden bg-chatgpt-hover">
      <ChatHeader title={notebookTitle} onRename={onRenameNotebook} />

      <ScrollArea className="flex-1 min-h-0" id="message-scroll-area">
        <div className="flex flex-col">
          <MessageList
            messages={currentMessages}
            isFetchingMessages={isFetchingMessages}
            isLoading={isLoading}
            currentThought={currentThought}
            lastMessageRef={lastMessageRef}
            bottomRef={bottomRef}
            handleRerunMessage={handleRerunMessage}
            handleDeleteUserPair={handleDeleteUserPair}
            inputValue={inputValue}
            setInputValue={setInputValue}
            handleSendMessage={handleSendMessage}
            interactionDisabled={interactionDisabled}
            selectedModel={selectedModel}
            setSelectedModel={setSelectedModel}
            models={availableModels}
            runningUserMessageId={runningUserMessageId}
            handleStopGeneration={handleStopGeneration}
          />

          {/* Editable user cell handled within MessageList */}
        </div>
      </ScrollArea>
    </main>
  );
} 