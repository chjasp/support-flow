"use client";

import React from 'react';
import { useSession } from 'next-auth/react';
import { Loader2, Trash2 } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { ChatMetadata } from '@/types';
import { SIDEBAR_TITLE_LIMIT } from '@/lib/constants';

interface SidebarProps {
  chatList: ChatMetadata[];
  activeChatId: string | null;
  handleNewChat: () => void;
  handleSelectChat: (id: string) => void;
  handleDeleteChat: (id: string) => void;
  isCreatingChat: boolean;
  isDeletingChat: boolean;
  isFetchingChats: boolean;
  interactionDisabled: boolean;
}

const truncateTitle = (title: string, maxLength: number = SIDEBAR_TITLE_LIMIT) => {
  if (title.length <= maxLength) return title;
  return title.slice(0, maxLength) + "...";
};

export function Sidebar({
  chatList,
  activeChatId,
  handleNewChat,
  handleSelectChat,
  handleDeleteChat,
  isCreatingChat,
  isDeletingChat,
  isFetchingChats,
  interactionDisabled,
}: SidebarProps) {
  const { data: session } = useSession();

  return (
    <aside className="flex flex-col bg-chatgpt-sidebar !w-52">
      {/* Logo */}
      <div className="h-12 flex items-center px-4 flex-shrink-0">
        <h1 className="text-xl font-semibold text-chatgpt">bloomlake</h1>
      </div>
      
      {/* Header Controls */}
      <div className="px-2 py-3 space-y-3">
        {/* Navigation Links */}
        <div className="flex flex-col gap-1 mb-2">
          <button
            onClick={handleNewChat}
            disabled={interactionDisabled}
            className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-chatgpt hover:bg-chatgpt-hover rounded-lg transition-colors cursor-pointer disabled:cursor-not-allowed"
          >
            {isCreatingChat ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
            )}
            New Chat
          </button>
          <button
            className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-chatgpt hover:bg-chatgpt-hover rounded-lg transition-colors cursor-pointer"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            Templates
          </button>
          <button
            className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-chatgpt hover:bg-chatgpt-hover rounded-lg transition-colors cursor-pointer"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            Upload
          </button>
          <button
            className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-chatgpt hover:bg-chatgpt-hover rounded-lg transition-colors cursor-pointer"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
            </svg>
            Data
          </button>
        </div>

      </div>

      {/* Chats Header */}
      <div className="px-5 py-2">
        <h3 className="text-sm text-chatgpt-secondary font-normal">Chats</h3>
      </div>

      {/* Conversation List */}
      <div className="flex-1 overflow-hidden">
        <ScrollArea className="h-full">
          {(isFetchingChats && session?.user) ? (
            <div className="p-4 text-center text-chatgpt-secondary text-sm">
              Loading chats...
            </div>
          ) : (
            <div className="space-y-1 p-2">
              {chatList.map((chat) => (
                <div
                  key={chat.id}
                  className={`w-full text-left px-3 h-[34px] flex items-center cursor-pointer rounded-lg text-sm font-normal transition-all relative group ${
                    chat.id === activeChatId
                      ? "bg-chatgpt-hover text-chatgpt"
                      : "text-chatgpt hover:bg-chatgpt-hover"
                  } ${interactionDisabled ? "cursor-not-allowed opacity-50" : ""}`}
                  onClick={() => !interactionDisabled && handleSelectChat(chat.id)}
                  title={chat.title} // Show full title on hover
                >
                  <div className="flex-1 flex items-center min-w-0">
                    <span className="flex-1 whitespace-nowrap overflow-hidden text-ellipsis">{truncateTitle(chat.title)}</span>
                  </div>
                  
                  {/* Delete button - shows on hover */}
                  <button
                    className="opacity-0 group-hover:opacity-100 flex-shrink-0 ml-2 p-1 hover:bg-red-600/20 rounded transition-all duration-200 cursor-pointer"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteChat(chat.id);
                    }}
                    disabled={interactionDisabled}
                  >
                    {isDeletingChat && chat.id === activeChatId ? (
                      <Loader2 className="h-3 w-3 animate-spin text-chatgpt-secondary" />
                    ) : (
                      <Trash2 className="h-3 w-3 text-chatgpt-secondary hover:text-red-400" />
                    )}
                  </button>
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </div>
    </aside>
  );
} 