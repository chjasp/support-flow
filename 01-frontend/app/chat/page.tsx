"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";

// Define a type for message objects
type Message = {
  id: number; // Unique within a single chat session
  text: string;
  sender: "user" | "bot";
};

// Define a type for a chat conversation
type Chat = {
  id: string; // Unique across all chats
  title: string;
  messages: Message[];
};

// Define constants
const MAX_TITLE_LENGTH = 30;
const BOT_RESPONSE_DELAY = 1000; // ms

// Define the initial message(s)
const initialBotMessage: Message = {
  id: 1,
  text: "Hello! How can I assist you with the knowledge base content today?",
  sender: "bot",
};

export default function ChatPage() {
  const [inputValue, setInputValue] = useState("");
  // State for all chat conversations
  const [allChats, setAllChats] = useState<Chat[]>([
    // Start with one initial chat
    { id: `chat-${Date.now()}`, title: "New Chat", messages: [initialBotMessage] },
  ]);
  // State for the currently active chat ID
  const [activeChatId, setActiveChatId] = useState<string | null>(allChats[0]?.id ?? null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const nextChatId = useRef(1); // Counter for new chat titles/IDs

  // Use useMemo to derive messages for the active chat efficiently
  const currentMessages = useMemo(() => {
    // Find the active chat and return its messages, or an empty array if no chat is active/found
    return allChats.find(chat => chat.id === activeChatId)?.messages ?? [];
  }, [allChats, activeChatId]); // Recalculate only when allChats or activeChatId changes

  // Function to scroll to the bottom of the messages
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  // useEffect to scroll down when messages change in the active chat
  useEffect(() => {
    scrollToBottom();
  }, [currentMessages]); // Depend on the memoized derived messages

  // Function to handle sending a message
  const handleSendMessage = () => {
    const trimmedInput = inputValue.trim();
    // Ensure there's input and an active chat
    if (!trimmedInput || !activeChatId) return;

    const newUserMessage: Message = {
      // Generate ID based on the current number of messages in the active chat.
      // Note: This assumes IDs only need to be unique *within the current session* for a chat.
      // For persistence, a more robust ID strategy (e.g., UUID) would be needed.
      id: (allChats.find(chat => chat.id === activeChatId)?.messages.length ?? 0) + 1,
      text: trimmedInput,
      sender: "user",
    };

    // 1. Update state: Add user message and potentially update chat title
    setAllChats(prevChats =>
      prevChats.map(chat => {
        if (chat.id === activeChatId) {
          const updatedMessages = [...chat.messages, newUserMessage];
          // Update title only if it's the first user message (after the initial bot message).
          // Check original length *before* adding the new user message.
          const newTitle = chat.messages.length === 1
            ? trimmedInput.substring(0, MAX_TITLE_LENGTH) + (trimmedInput.length > MAX_TITLE_LENGTH ? '...' : '')
            : chat.title;
          return { ...chat, title: newTitle, messages: updatedMessages };
        }
        return chat;
      })
    );

    setInputValue(""); // Clear input field immediately

    // 2. Simulate Bot Response after a delay
    setTimeout(() => {
      // Use the functional update form of setAllChats to ensure we have the latest state
      // when calculating the bot message ID and adding the message, avoiding potential race conditions.
      setAllChats(currentChats =>
        currentChats.map(chat => {
          if (chat.id === activeChatId) {
            // Create bot response - ID depends on the length *after* user message was added
            const botResponse: Message = {
              id: chat.messages.length + 1, // ID based on the latest message count
              text: `Echo: ${trimmedInput}`, // Simple echo response
              sender: "bot",
            };
            // Add bot response to the messages array
            return { ...chat, messages: [...chat.messages, botResponse] };
          }
          return chat;
        })
      );
    }, BOT_RESPONSE_DELAY); // Use constant for delay
  };

  // Handle Enter key press in the input field
  const handleKeyPress = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      handleSendMessage();
    }
  };

  // Function to start a new chat
  const handleNewChat = () => {
    // Generate a unique ID for the new chat using timestamp and counter
    const newChatId = `chat-${Date.now()}-${nextChatId.current}`;
    const newChat: Chat = {
      id: newChatId,
      title: `New Chat ${nextChatId.current}`, // Simple title using the counter
      messages: [initialBotMessage], // Start with the initial bot message
    };
    nextChatId.current++; // Increment the counter for the next new chat
    // Prepend the new chat to the list (newest first) and set it as active
    setAllChats(prevChats => [newChat, ...prevChats]);
    setActiveChatId(newChatId);
    setInputValue(""); // Clear input field for the new chat
  };

  // Function to switch to a different chat
  const handleSelectChat = (chatId: string) => {
    setActiveChatId(chatId);
  };


  return (
    <div className="flex h-[calc(100vh-theme(spacing.14)-theme(spacing.6))] border rounded-lg overflow-hidden">
      <aside className="w-64 md:w-72 border-r flex flex-col bg-muted/30">
        <div className="p-4 border-b">
          <h2 className="text-lg font-semibold tracking-tight">Recent Chats</h2>
        </div>
        <ScrollArea className="flex-1 p-2 min-h-0">
          <nav className="flex flex-col gap-1">
            {/* Map over allChats to display history */}
            {allChats.map((chat) => (
              <Button
                key={chat.id}
                variant="ghost"
                className={`justify-start w-full text-left h-auto py-2 px-3 ${
                  chat.id === activeChatId ? 'bg-accent text-accent-foreground' : '' // Highlight active chat
                }`}
                onClick={() => handleSelectChat(chat.id)} // Select chat on click
              >
                <span className="truncate">{chat.title}</span> {/* Display chat title */}
              </Button>
            ))}
          </nav>
        </ScrollArea>
        <div className="p-4 border-t mt-auto">
           <Button className="w-full" onClick={handleNewChat}>New Chat</Button>
        </div>
      </aside>
      <main className="flex-1 flex flex-col overflow-hidden">
        <div className="p-4 border-b flex items-center justify-between bg-background/95">
           {/* Display title of the active chat, or a default */}
           <h1 className="text-xl font-bold tracking-tight">
             {allChats.find(chat => chat.id === activeChatId)?.title ?? "Chat"}
           </h1>
        </div>
        <ScrollArea className="flex-1 p-4 min-h-0">
          <div className="space-y-4">
            {/* Render messages from the derived currentMessages */}
            {currentMessages.map((message, index) => ( // Use index for key if message IDs aren't stable across renders yet
              <div
                key={`${activeChatId}-msg-${message.id}-${index}`} // More robust key using chat ID, message ID, and index
                className={`flex ${
                  message.sender === "user" ? "justify-end" : "justify-start"
                }`}
              >
                <div
                  className={`p-3 max-w-[75%] text-sm rounded-lg ${ // Adjusted rounding for consistency
                    message.sender === "user"
                      ? "bg-muted text-white" // User bubble: Use muted background and white text
                      : "bg-transparent" // Bot bubble: Use transparent background
                  }`}
                >
                  <p>{message.text}</p>
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        </ScrollArea>
        <div className="p-4 border-t bg-background">
          {/* Input area remains largely the same */}
          <div className="flex items-center gap-2">
            <Input
              type="text"
              placeholder="Ask a question..." // Simplified placeholder
              className="flex-1"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyPress={handleKeyPress}
              disabled={!activeChatId} // Disable input if no chat is active
            />
            <Button onClick={handleSendMessage} disabled={!activeChatId || !inputValue.trim()}>Send</Button> {/* Disable send if no active chat or input */}
          </div>
        </div>
      </main>
    </div>
  );
}
