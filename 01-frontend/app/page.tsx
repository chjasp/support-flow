"use client";

import React from "react";
import { useChat } from "@/hooks/useChat";
import { Sidebar } from "@/components/chat/Sidebar";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { useSession } from "next-auth/react";
import { Loader2 } from "lucide-react";

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
    currentThought,
    handleRerunMessage,
    selectedModel,
    setSelectedModel,
    handleDeleteUserPair,
    availableModels,
    handleRenameChat,
    runningUserMessageId,
  } = useChat();

  const activeChat = chatList.find((c) => c.id === activeChatId);
  const activeTitle = activeChat?.title || "Untitled Notebook";

  if (status === "loading") {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-chatgpt-main">
        <Loader2 className="h-8 w-8 animate-spin text-chatgpt" />
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
        currentThought={currentThought}
        handleRerunMessage={handleRerunMessage}
        selectedModel={selectedModel}
        setSelectedModel={setSelectedModel}
        handleDeleteUserPair={handleDeleteUserPair}
        availableModels={availableModels}
        notebookTitle={activeTitle}
        onRenameNotebook={(title: string) => {
          if (activeChatId) {
            handleRenameChat(activeChatId, title);
          }
        }}
        runningUserMessageId={runningUserMessageId}
      />
    </div>
  );
}
