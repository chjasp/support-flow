"use client";

import React from "react";
import { useChat } from "@/hooks/useChat";
import { Sidebar } from "@/components/chat/Sidebar";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { useSession } from "next-auth/react";

export default function HomePage() {
  const { status } = useSession();
  const {
    inputValue,
    setInputValue,
    chatList,
    currentMessages,
    activeChatId,
    isLoading,
    isGenerating,
    isFetchingChats,
    isFetchingMessages,
    isCreatingChat,
    isDeletingChat,
    interactionDisabled,
    handleNewChat,
    handleSelectChat,
    handleDeleteChat,
    handleSendMessage,
    handleStopGeneration,
    activeTypingMessageId,
  } = useChat();

  if (status === "loading") {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-chatgpt-main">
        <h1 className="text-xl text-chatgpt">Loading session ...</h1>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-full overflow-hidden bg-chatgpt-main">
      <Sidebar
        chatList={chatList}
        activeChatId={activeChatId}
        handleNewChat={handleNewChat}
        handleSelectChat={handleSelectChat}
        handleDeleteChat={handleDeleteChat}
        isCreatingChat={isCreatingChat}
        isDeletingChat={isDeletingChat}
        isFetchingChats={isFetchingChats}
        interactionDisabled={interactionDisabled}
      />
      <ChatPanel
        currentMessages={currentMessages}
        isFetchingMessages={isFetchingMessages}
        isLoading={isLoading}
        isGenerating={isGenerating}
        inputValue={inputValue}
        setInputValue={setInputValue}
        handleSendMessage={handleSendMessage}
        handleStopGeneration={handleStopGeneration}
        interactionDisabled={interactionDisabled}
        activeChatId={activeChatId}
        activeTypingMessageId={activeTypingMessageId}
      />
    </div>
  );
}
