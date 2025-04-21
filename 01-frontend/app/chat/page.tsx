"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Loader2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";

// --- Define Types (Align with Backend) ---
type Message = {
  id: string; // Firestore document ID
  text: string;
  sender: "user" | "bot";
  timestamp: string; // Store as ISO string or Date object
};

// Type for chat metadata list
type ChatMetadata = {
  id: string;
  title: string;
  createdAt: string; // ISO string
  lastActivity: string; // ISO string
};

// --- Constants ---
const MAX_TITLE_LENGTH = 30; // Keep consistent with backend if used there
const BACKEND_API_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:5147";

export default function ChatPage() {
  const [inputValue, setInputValue] = useState("");
  // State for chat list metadata
  const [chatList, setChatList] = useState<ChatMetadata[]>([]);
  // State for messages of the currently active chat
  const [currentMessages, setCurrentMessages] = useState<Message[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false); // For sending messages
  const [isFetchingChats, setIsFetchingChats] = useState(true); // For initial chat list load
  const [isFetchingMessages, setIsFetchingMessages] = useState(false); // For loading messages of a chat
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // --- API Endpoints ---
  const CHATS_ENDPOINT = `${BACKEND_API_URL}/chats`;
  const getMessagesEndpoint = (chatId: string) => `${CHATS_ENDPOINT}/${chatId}/messages`;
  const postMessageEndpoint = (chatId: string) => `${BACKEND_API_URL}/chat/${chatId}`; // Note the change

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [currentMessages]); // Scroll when messages change

  // --- Fetch Messages for a Specific Chat ---
  const fetchMessages = useCallback(async (chatId: string) => {
    if (!chatId) return;
    console.log(`Fetching messages for chat: ${chatId}`);
    setIsFetchingMessages(true);
    setCurrentMessages([]); // Clear previous messages
    try {
      const response = await fetch(getMessagesEndpoint(chatId));
      if (!response.ok) {
        throw new Error(`Failed to fetch messages: ${response.statusText}`);
      }
      const messagesData: Message[] = await response.json();
       // Convert timestamp strings to Date objects if needed, or keep as strings
      const formattedMessages = messagesData.map(msg => ({
          ...msg,
          // Example: Convert to Date if you prefer working with Date objects
          // timestamp: new Date(msg.timestamp)
      }));
      setCurrentMessages(formattedMessages);
      console.log(`Loaded ${formattedMessages.length} messages for chat ${chatId}`);
    } catch (error) {
      console.error("Error fetching messages:", error);
      setCurrentMessages([]); // Clear messages on error
      // TODO: Show error to user
    } finally {
      setIsFetchingMessages(false);
    }
  }, []); // Dependencies: BACKEND_API_URL could be added if it changes, but usually doesn't

  // --- Initial Load: Fetch Chat List ---
  useEffect(() => {
    const loadInitialChats = async () => {
      console.log("Fetching initial chat list...");
      setIsFetchingChats(true);
      setChatList([]);
      setActiveChatId(null);
      setCurrentMessages([]);
      try {
        const response = await fetch(CHATS_ENDPOINT);
        if (!response.ok) {
          throw new Error(`Failed to fetch chats: ${response.statusText}`);
        }
        const chatsData: ChatMetadata[] = await response.json();

        if (chatsData && chatsData.length > 0) {
          console.log(`Found ${chatsData.length} existing chats.`);
          setChatList(chatsData);
          // Activate the most recent chat (first in the list due to backend sorting)
          const mostRecentChatId = chatsData[0].id;
          setActiveChatId(mostRecentChatId);
          // Fetch messages for the activated chat
          await fetchMessages(mostRecentChatId);
        } else {
          console.log("No existing chats found. Creating a new one.");
          // If no chats exist, create the very first one
          await handleNewChat(); // handleNewChat now fetches messages internally
        }
      } catch (error) {
        console.error("Error fetching initial chats:", error);
        // Optionally try creating a new chat even if fetching failed
        // await handleNewChat();
        // TODO: Show error to user
      } finally {
        setIsFetchingChats(false);
      }
    };

    loadInitialChats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchMessages]); // Add fetchMessages, handleNewChat isn't stable here yet

  // --- Function to Start a New Chat ---
  const handleNewChat = useCallback(async () => {
    console.log("Creating new chat via API...");
    setIsLoading(true); // Use main loading indicator briefly
    try {
      const response = await fetch(CHATS_ENDPOINT, { method: "POST" });
      if (!response.ok) {
        throw new Error(`Failed to create new chat: ${response.statusText}`);
      }
      const newChatData: { id: string; title: string; messages: Message[] } = await response.json();

      console.log(`New chat created with ID: ${newChatData.id}`);

      // Add new chat metadata to the beginning of the list
      const newMetadata: ChatMetadata = {
          id: newChatData.id,
          title: newChatData.title,
          // Approximate client-side times, backend has the accurate ones
          createdAt: new Date().toISOString(),
          lastActivity: new Date().toISOString(),
      }
      setChatList((prev) => [newMetadata, ...prev]);

      // Activate the new chat
      setActiveChatId(newChatData.id);
      // Set the initial messages returned by the API
      setCurrentMessages(newChatData.messages);
      setInputValue(""); // Clear input

    } catch (error) {
      console.error("Error creating new chat:", error);
      // TODO: Show error to user
    } finally {
      setIsLoading(false);
    }
  }, []); // Dependencies: CHATS_ENDPOINT

  // --- Function to Switch Active Chat ---
  const handleSelectChat = (chatId: string) => {
    if (chatId === activeChatId) return; // Do nothing if already active
    console.log(`Switching to chat: ${chatId}`);
    setActiveChatId(chatId);
    // Fetch messages for the newly selected chat
    fetchMessages(chatId);
  };

  // --- Function to Handle Sending a Message ---
  const handleSendMessage = async () => {
    const trimmedInput = inputValue.trim();
    if (!trimmedInput || !activeChatId || isLoading || isFetchingMessages) return;

    console.log(`Sending message to chat ${activeChatId}: ${trimmedInput}`);
    setIsLoading(true);
    setInputValue(""); // Clear input immediately

    // --- No Optimistic UI for user message initially ---
    // We will refresh the whole message list after backend confirmation

    try {
      // 1. Call Backend API to process query and save messages
      const response = await fetch(postMessageEndpoint(activeChatId), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: trimmedInput }),
      });

      if (!response.ok) {
        // Try to get error details
        let errorDetails = `Error: ${response.status} ${response.statusText}`;
        try {
          const errorData = await response.json();
          errorDetails = errorData.detail || errorDetails;
        } catch (e) { /* Ignore if response not JSON */ }
        throw new Error(`Backend query failed: ${errorDetails}`);
      }

      // Backend handled saving user & bot message. Response is QueryResponse.
      const queryResponse = await response.json(); // Contains answer, chunks
      console.log("Backend processed message successfully.");

      // 2. Re-fetch messages for the current chat to update UI
      await fetchMessages(activeChatId);

      // 3. Update chat list metadata (title might have changed, lastActivity definitely did)
      // Find the chat in the list and update its title/activity time
      setChatList(prevList => prevList.map(chat => {
          if (chat.id === activeChatId) {
              // Attempt to update title if it was "New Chat" - check currentMessages
              // This is a bit indirect. Ideally, the POST response could include the new title.
              const potentialNewTitle = trimmedInput.substring(0, MAX_TITLE_LENGTH) +
                  (trimmedInput.length > MAX_TITLE_LENGTH ? "..." : "");
              const currentTitle = chat.title === "New Chat" ? potentialNewTitle : chat.title;

              return { ...chat, title: currentTitle, lastActivity: new Date().toISOString() };
          }
          return chat;
      }).sort((a, b) => new Date(b.lastActivity).getTime() - new Date(a.lastActivity).getTime()) // Re-sort by activity
      );


    } catch (error) {
      console.error("Failed to send message or fetch update:", error);
      // Add an error message locally? Or rely on fetchMessages error handling?
      // Example: Add a temporary local error message
      const errorTimestamp = new Date().toISOString();
      const errorMessage: Message = {
        id: `error-${errorTimestamp}`,
        text: `Sorry, failed to send message. ${error instanceof Error ? error.message : 'Please try again.'}`,
        sender: "bot", // Display as a bot message for consistency
        timestamp: errorTimestamp,
      };
      setCurrentMessages((prev) => [...prev, errorMessage]);
      // TODO: Better error display (e.g., toast)
    } finally {
      setIsLoading(false);
    }
  };

  // Handle Enter key press
  const handleKeyPress = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSendMessage();
    }
  };

  // --- Get Active Chat Title ---
  const activeChatTitle = chatList.find(chat => chat.id === activeChatId)?.title ?? "Chat";

  // --- Render Logic ---
  return (
    <div className="flex h-[calc(100vh-theme(spacing.14)-theme(spacing.6))] border rounded-lg overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 md:w-72 border-r flex flex-col bg-muted/30">
        <div className="p-4 border-b">
          <h2 className="text-lg font-semibold tracking-tight">Recent Chats</h2>
        </div>
        <ScrollArea className="flex-1 p-2 min-h-0">
          {isFetchingChats ? (
            <div className="p-4 text-center text-muted-foreground">Loading chats...</div>
          ) : (
            <nav className="flex flex-col gap-1">
              {chatList.map((chat) => (
                <Button
                  key={chat.id}
                  variant="ghost"
                  className={`justify-start w-full text-left h-auto py-2 px-3 ${
                    chat.id === activeChatId
                      ? "bg-accent text-accent-foreground"
                      : ""
                  }`}
                  onClick={() => handleSelectChat(chat.id)}
                  disabled={isFetchingMessages || isLoading} // Disable while loading/sending
                >
                  <span className="truncate">{chat.title}</span>
                </Button>
              ))}
            </nav>
          )}
        </ScrollArea>
        <div className="p-4 border-t mt-auto">
          <Button
            className="w-full"
            onClick={handleNewChat}
            disabled={isLoading || isFetchingChats || isFetchingMessages} // Disable while loading
          >
            New Chat
          </Button>
        </div>
      </aside>

      {/* Main Chat Area */}
      <main className="flex-1 flex flex-col overflow-hidden">
        <div className="p-4 border-b flex items-center justify-between bg-background/95">
          <h1 className="text-xl font-bold tracking-tight truncate">
            {activeChatTitle}
          </h1>
          {/* Maybe add a delete chat button here later */}
        </div>
        <ScrollArea className="flex-1 p-4 min-h-0" id="message-scroll-area">
          <div className="space-y-4">
            {isFetchingMessages && (
              <div className="flex justify-center items-center p-4">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                <span className="ml-2 text-muted-foreground">Loading messages...</span>
              </div>
            )}
            {!isFetchingMessages && currentMessages.map((message, index) => (
              <div
                // Use Firestore message ID for the key
                key={message.id || `msg-${index}`} // Fallback index key if id is missing somehow
                className={`flex ${
                  message.sender === "user" ? "justify-end" : "justify-start"
                }`}
              >
                <div
                  className={`p-3 max-w-[75%] text-sm rounded-lg ${
                    message.sender === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted"
                  }`}
                >
                  {/* Render Markdown for both user and bot */}
                  <div className="prose prose-sm dark:prose-invert max-w-none break-words">
                     <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                       {message.text}
                     </ReactMarkdown>
                  </div>
                </div>
              </div>
            ))}
            {/* Loading indicator when waiting for bot response */}
            {isLoading && activeChatId && (
              <div className="flex justify-start">
                <div className="p-3 max-w-[75%] text-sm rounded-lg bg-muted flex items-center space-x-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>Thinking...</span>
                </div>
              </div>
            )}
            {/* End of messages ref */}
            <div ref={messagesEndRef} />
          </div>
        </ScrollArea>
        <div className="p-4 border-t bg-background/95">
          <div className="relative">
            <Input
              type="text"
              placeholder="Type your message..."
              className="pr-16" // Make space for the button
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyPress={handleKeyPress}
              disabled={isLoading || isFetchingMessages || isFetchingChats || !activeChatId} // Disable input when loading/no active chat
            />
            <Button
              type="submit" // Can be submit if wrapped in a form, or just button
              size="icon"
              className="absolute right-2 top-1/2 -translate-y-1/2 h-8 w-8"
              onClick={handleSendMessage}
              disabled={isLoading || isFetchingMessages || isFetchingChats || !activeChatId || !inputValue.trim()}
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5"><path d="M3.478 2.404a.75.75 0 0 0-.926.941l2.432 7.905H13.5a.75.75 0 0 1 0 1.5H4.984l-2.432 7.905a.75.75 0 0 0 .926.94 60.519 60.519 0 0 0 18.445-8.986.75.75 0 0 0 0-1.218A60.517 60.517 0 0 0 3.478 2.404Z" /></svg>
              <span className="sr-only">Send</span>
            </Button>
          </div>
        </div>
      </main>
    </div>
  );
}
