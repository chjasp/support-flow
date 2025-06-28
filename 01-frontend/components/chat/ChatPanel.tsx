"use client";

import React, { useRef, useEffect } from 'react';
import { useSession, signOut, signIn } from 'next-auth/react';
import { LogIn, LogOut } from 'lucide-react';
import { Message } from '@/types';
import { ScrollArea } from '@/components/ui/scroll-area';
import { MessageList } from '@/components/chat/MessageList';
import { ChatInput } from '@/components/chat/ChatInput';
import * as Select from '@radix-ui/react-select';
import { ChevronDown, Check } from 'lucide-react';

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
}

function ChatHeader({ selectedModel, setSelectedModel }: { selectedModel: string; setSelectedModel: React.Dispatch<React.SetStateAction<string>> }) {
  const { data: session } = useSession();
  return (
    <div className="bg-chatgpt-hover h-12 flex items-center justify-between px-4 flex-shrink-0">
      {/* Custom select using Radix for full styling control */}
      <Select.Root value={selectedModel} onValueChange={setSelectedModel}>
        <Select.Trigger className="flex items-center gap-1 text-chatgpt text-sm focus:outline-none cursor-pointer" aria-label="Model selector">
          <Select.Value />
          <Select.Icon asChild>
            <ChevronDown className="w-4 h-4" />
          </Select.Icon>
        </Select.Trigger>
        <Select.Portal>
          <Select.Content className="bg-chatgpt-sidebar text-chatgpt border border-chatgpt-border rounded-md shadow-lg overflow-hidden">
            <Select.Viewport className="py-1">
              {['Gemini 2.5 Pro', 'Gemini 2.5 Flash', 'Gemini 2.5 Flash Lite'].map((model) => (
                <Select.Item
                  key={model}
                  value={model}
                  className="cursor-pointer px-4 py-1 text-sm flex items-center gap-2 outline-none data-[highlighted]:bg-chatgpt-hover"
                >
                  <Select.ItemText>{model}</Select.ItemText>
                  <Select.ItemIndicator className="ml-auto">
                    <Check className="w-4 h-4" />
                  </Select.ItemIndicator>
                </Select.Item>
              ))}
            </Select.Viewport>
          </Select.Content>
        </Select.Portal>
      </Select.Root>

      {/* Sign out button on the right */}
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
        <ChatHeader selectedModel={selectedModel} setSelectedModel={setSelectedModel} />
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
      <ChatHeader selectedModel={selectedModel} setSelectedModel={setSelectedModel} />

      <ScrollArea className="flex-1 min-h-0" id="message-scroll-area">
        <MessageList
          messages={currentMessages}
          isFetchingMessages={isFetchingMessages}
          isLoading={isLoading}
          currentThought={currentThought}
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