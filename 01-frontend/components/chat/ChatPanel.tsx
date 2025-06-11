"use client";

import React, { useRef, useEffect } from 'react';
import { useSession, signOut, signIn } from 'next-auth/react';
import { LogIn } from 'lucide-react';
import { Message } from '@/types';
import { ScrollArea } from '@/components/ui/scroll-area';
import { MessageList } from '@/components/chat/MessageList';
import { ChatInput } from '@/components/chat/ChatInput';

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
}

function ChatHeader() {
  const { data: session } = useSession();
  return (
    <div className="bg-chatgpt-hover h-12 flex items-center justify-end px-4 flex-shrink-0">
      {session?.user && (
        <button
          onClick={() => signOut()}
          className="w-7 h-7 bg-chatgpt-accent rounded-full flex items-center justify-center text-sm font-medium text-white hover:opacity-80 transition-opacity"
          title={`${session.user.name ?? session.user.email} - Click to sign out`}
        >
          {session.user.name?.charAt(0) || session.user.email?.charAt(0) || 'U'}
        </button>
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
}: ChatPanelProps) {
  const { data: session, status } = useSession();
  const lastMessageRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (lastMessageRef.current) {
      lastMessageRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [currentMessages.length]);

  if (status !== 'loading' && !session?.user) {
    return (
      <main className="flex-1 flex flex-col overflow-hidden bg-chatgpt-hover">
        <ChatHeader />
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
      <ChatHeader />

      <ScrollArea className="flex-1 min-h-0" id="message-scroll-area">
        <MessageList
          messages={currentMessages}
          isFetchingMessages={isFetchingMessages}
          isLoading={isLoading}
          lastMessageRef={lastMessageRef}
          bottomRef={bottomRef}
        />
      </ScrollArea>

      <ChatInput
        inputValue={inputValue}
        setInputValue={setInputValue}
        handleSendMessage={handleSendMessage}
        handleStopGeneration={handleStopGeneration}
        isLoading={isLoading}
        isGenerating={isGenerating}
        interactionDisabled={interactionDisabled}
        activeChatId={activeChatId}
        activeTypingMessageId={activeTypingMessageId}
      />
    </main>
  );
} 