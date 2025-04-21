"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Loader2, Trash2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";

// --- Define Types (Align with Backend) ---
type Message = {
  id: string; // Firestore document ID
  text: string;
  sender: "user" | "bot";
  timestamp: string; // Store as ISO string (Firestore returns Date, fetch converts)
};

// Type for chat metadata list
type ChatMetadata = {
  id: string;
  title: string;
  // createdAt: string; // Optional: if needed for display
  lastActivity: string; // ISO string
};

// --- Constants ---
const MAX_TITLE_LENGTH = 30; // Keep consistent with backend if used there
const BACKEND_API_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8080"; // Ensure port matches backend (8080 default)

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
  const [isCreatingChat, setIsCreatingChat] = useState(false);
  const [isDeletingChat, setIsDeletingChat] = useState(false); // <-- Add state for delete operation
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // --- API Endpoints ---
  const CHATS_ENDPOINT = `${BACKEND_API_URL}/chats`;
  const getMessagesEndpoint = (chatId: string) => `${CHATS_ENDPOINT}/${chatId}/messages`;
  const postMessageEndpoint = (chatId: string) => `${BACKEND_API_URL}/chat/${chatId}`;
  const deleteChatEndpoint = (chatId: string) => `${CHATS_ENDPOINT}/${chatId}`; // <-- Add delete endpoint URL

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [currentMessages]);

  // --- Fetch Messages for a Specific Chat ---
  const fetchMessages = useCallback(async (chatId: string) => {
    if (!chatId) return;
    console.log(`Fetching messages for chat: ${chatId}`);
    setIsFetchingMessages(true);
    setCurrentMessages([]); // Clear messages when switching chats
    try {
      const response = await fetch(getMessagesEndpoint(chatId));
      if (!response.ok) {
         // Handle 404 specifically maybe?
         if (response.status === 404) {
            console.error(`Chat not found on backend: ${chatId}`);
            // TODO: Handle this - maybe remove chat from list or show error
            // If a chat is not found when fetching messages, remove it from the list
            setChatList(prev => prev.filter(chat => chat.id !== chatId));
            setActiveChatId(null); // Deactivate
            // Optionally select the next chat or create a new one
            // For now, just clear the view
         }
         throw new Error(`Failed to fetch messages: ${response.statusText}`);
      }
      const messagesData: Message[] = await response.json();
       // Timestamps from Firestore via FastAPI should be ISO strings
      // Sort client-side just in case, though backend should order
      messagesData.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
      // This will replace the optimistic message + any previous state
      setCurrentMessages(messagesData);
      console.log(`Loaded ${messagesData.length} messages for chat ${chatId}`);
    } catch (error) {
      console.error("Error fetching messages:", error);
      // TODO: Show error to user (e.g., toast notification) without clearing chat
    } finally {
      setIsFetchingMessages(false);
    }
  }, []); // <-- fetchMessages is stable

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

        // Backend already sorts by lastActivity descending
        setChatList(chatsData);

        if (chatsData && chatsData.length > 0) {
          console.log(`Found ${chatsData.length} existing chats.`);
          // Activate the most recent chat (first in the list)
          const mostRecentChatId = chatsData[0].id;
          setActiveChatId(mostRecentChatId);
          // Fetch messages for the activated chat
          await fetchMessages(mostRecentChatId); // fetchMessages is now stable
        } else {
          console.log("No existing chats found. Creating a new one.");
          // If no chats exist, create the very first one
          await handleNewChat(); // handleNewChat now fetches messages internally
        }
      } catch (error) {
        console.error("Error fetching initial chats:", error);
        // Optionally try creating a new chat even if fetching failed
        // await handleNewChat(); // Be careful not to loop infinitely on errors
        // TODO: Show error to user
      } finally {
        setIsFetchingChats(false);
      }
    };

    loadInitialChats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchMessages]); // <-- Add fetchMessages dependency

  // --- Function to Start a New Chat ---
  const handleNewChat = useCallback(async () => {
    console.log("Creating new chat via API...");
    setIsCreatingChat(true); // <-- Use the new state
    try {
      const response = await fetch(CHATS_ENDPOINT, { method: "POST" });
      if (!response.ok) {
        throw new Error(`Failed to create new chat: ${response.statusText}`);
      }
      // Backend response includes id, title, and initial messages
      const newChatData: { id: string; title: string; messages: Message[] } = await response.json();

      console.log(`New chat created with ID: ${newChatData.id}`);

      // Add new chat metadata to the beginning of the list
      const newMetadata: ChatMetadata = {
          id: newChatData.id,
          title: newChatData.title,
          // Approximate client-side time, backend has the accurate ones
          // Fetching the list again would be more accurate but slower
          lastActivity: new Date().toISOString(),
      }
      // Prepend to list
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
      setIsCreatingChat(false); // <-- Use the new state
    }
  }, []); // No dependencies needed if CHATS_ENDPOINT is stable

  // --- Function to Switch Active Chat ---
  const handleSelectChat = (chatId: string) => {
    if (chatId === activeChatId || isDeletingChat) return; // Do nothing if already active or deleting
    console.log(`Switching to chat: ${chatId}`);
    setActiveChatId(chatId);
    // Fetch messages for the newly selected chat
    fetchMessages(chatId);
  };

  // --- Function to Handle Sending a Message ---
  const handleSendMessage = async () => {
    const trimmedInput = inputValue.trim();
    if (!trimmedInput || !activeChatId || isLoading || isFetchingMessages || isDeletingChat) return;

    console.log(`Sending message to chat ${activeChatId}: ${trimmedInput}`);
    setInputValue(""); // Clear input immediately after grabbing value

    // --- Optimistic UI Update ---
    const optimisticUserMessage: Message = {
      // Use a temporary ID, backend response will provide the real one via fetchMessages
      id: `temp-${Date.now()}`,
      text: trimmedInput,
      sender: "user",
      timestamp: new Date().toISOString(), // Use current time for optimistic display
    };

    // Add user message immediately
    setCurrentMessages((prevMessages) => [...prevMessages, optimisticUserMessage]);

    setIsLoading(true); // Show "Thinking..." indicator *after* user message

    try {
      // 1. Call Backend API to process query and save messages
      //    The endpoint now includes the chat_id
      const response = await fetch(postMessageEndpoint(activeChatId), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: trimmedInput }), // Send original trimmed input
      });

      if (!response.ok) {
        // Try to get error details
        let errorDetails = `Error: ${response.status} ${response.statusText}`;
        try {
          const errorData = await response.json();
          errorDetails = errorData.detail || errorDetails;
        } catch (e) { /* Ignore if response not JSON */ }
        // Remove the optimistic message on backend error before throwing
        setCurrentMessages((prev) => prev.filter(msg => msg.id !== optimisticUserMessage.id));
        throw new Error(`Backend query failed: ${errorDetails}`);
      }

      // Backend handled saving user & bot message. Response is QueryResponse.
      // We don't *need* the response data here if we re-fetch messages.
      // const queryResponse = await response.json(); // Contains answer, chunks
      await response.json(); // Still need to consume the response body
      console.log("Backend processed message successfully.");

      // 2. Re-fetch messages for the current chat to update UI *reliably*
      // This will replace the optimistic message with the real one from the DB
      // and add the bot's response.
      await fetchMessages(activeChatId);

      // 3. Update chat list metadata (title might have changed, lastActivity definitely did)
      //    Find the chat in the list and update its title/activity time
      setChatList(prevList => {
          const chatIndex = prevList.findIndex(chat => chat.id === activeChatId);
          if (chatIndex === -1) return prevList; // Should not happen

          const updatedChat = { ...prevList[chatIndex] };
          updatedChat.lastActivity = new Date().toISOString(); // Update activity time

          // Check if title needs update (was "New Chat")
          // Use the optimistic message text for potential title update
          if (updatedChat.title === "New Chat") {
              const potentialNewTitle = optimisticUserMessage.text.substring(0, MAX_TITLE_LENGTH) +
                  (optimisticUserMessage.text.length > MAX_TITLE_LENGTH ? "..." : "");
              updatedChat.title = potentialNewTitle;
          }

          // Create new list, move updated chat to top, keep rest sorted by original fetch order (or re-sort)
          const newList = [
              updatedChat,
              ...prevList.slice(0, chatIndex),
              ...prevList.slice(chatIndex + 1)
          ];
          // Optionally re-sort the whole list by lastActivity again if strict order is needed
          // newList.sort((a, b) => new Date(b.lastActivity).getTime() - new Date(a.lastActivity).getTime());
          return newList;
      });


    } catch (error) {
      console.error("Failed to send message or fetch update:", error);
      // Error message is now added *after* the optimistic message might have been removed
      const errorTimestamp = new Date().toISOString();
      const errorMessage: Message = {
        id: `error-${errorTimestamp}`, // Temporary ID
        text: `Sorry, failed to send message. ${error instanceof Error ? error.message : 'Please try again.'}`,
        sender: "bot", // Display as a bot message for consistency
        timestamp: errorTimestamp,
      };
      // Append the error message locally for immediate feedback
      // Check if the optimistic message still exists before adding the error
      setCurrentMessages((prev) => {
          // If the optimistic message wasn't removed by the specific backend error handling,
          // keep it and add the error. Otherwise, just add the error.
          const optimisticExists = prev.some(msg => msg.id === optimisticUserMessage.id);
          if (optimisticExists) {
              return [...prev, errorMessage];
          } else {
              // If the optimistic message was already removed due to backend error,
              // find the last actual message to add the error after.
              // This part might need refinement based on desired UX for cascading errors.
              // For simplicity now, just add the error to the end.
              return [...prev, errorMessage];
          }
      });
      // TODO: Better error display (e.g., toast)
    } finally {
      // This will remove the "Thinking..." indicator after fetchMessages completes or an error occurs.
      setIsLoading(false);
    }
  };

  // --- Function to Handle Deleting a Chat ---
  const handleDeleteChat = async (chatIdToDelete: string) => {
    if (!chatIdToDelete || isDeletingChat) return;

    // Simple confirmation dialog
    if (!window.confirm("Are you sure you want to delete this chat and all its messages? This cannot be undone.")) {
        return;
    }

    console.log(`Attempting to delete chat: ${chatIdToDelete}`);
    setIsDeletingChat(true);

    try {
        const response = await fetch(deleteChatEndpoint(chatIdToDelete), {
            method: "DELETE",
        });

        if (!response.ok) {
            let errorDetails = `Error: ${response.status} ${response.statusText}`;
            if (response.status === 404) {
                errorDetails = "Chat not found on server.";
                // Remove from list even if server says 404, might be out of sync
                setChatList(prev => prev.filter(chat => chat.id !== chatIdToDelete));
            } else {
                try {
                    const errorData = await response.json();
                    errorDetails = errorData.detail || errorDetails;
                } catch (e) { /* Ignore if response not JSON */ }
            }
            throw new Error(`Failed to delete chat: ${errorDetails}`);
        }

        console.log(`Successfully deleted chat: ${chatIdToDelete}`);

        // Update chat list state
        const remainingChats = chatList.filter(chat => chat.id !== chatIdToDelete);
        setChatList(remainingChats);

        // If the deleted chat was the active one, select the next available chat
        if (activeChatId === chatIdToDelete) {
            if (remainingChats.length > 0) {
                // Activate the most recent remaining chat (first in the list)
                const nextChatId = remainingChats[0].id;
                setActiveChatId(nextChatId);
                await fetchMessages(nextChatId); // Load messages for the new active chat
            } else {
                // No chats left, create a new one
                setActiveChatId(null);
                setCurrentMessages([]);
                await handleNewChat(); // Create a fresh chat
            }
        }
        // If a different chat was active, no need to change activeChatId or messages

    } catch (error) {
        console.error("Error deleting chat:", error);
        // TODO: Show error to user (e.g., toast notification)
        alert(`Failed to delete chat: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
        setIsDeletingChat(false);
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
                  disabled={isFetchingMessages || isLoading || isFetchingChats || isCreatingChat || isDeletingChat} // <-- Disable during delete
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
            disabled={isLoading || isFetchingChats || isFetchingMessages || isCreatingChat || isDeletingChat} // <-- Disable during delete
          >
            {isCreatingChat ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            New Chat
          </Button>
        </div>
      </aside>

      {/* Main Chat Area */}
      <main className="flex-1 flex flex-col overflow-hidden">
        <div className="p-4 border-b flex items-center justify-between bg-background/95">
          <h1 className="text-xl font-bold tracking-tight truncate mr-2"> {/* Added margin-right */}
            {activeChatTitle}
          </h1>
          {/* Delete Chat Button */}
          {activeChatId && ( // Only show if a chat is active
            <Button
              variant="ghost"
              size="icon"
              onClick={() => handleDeleteChat(activeChatId)}
              disabled={isDeletingChat || isFetchingChats || isCreatingChat} // Disable while deleting/loading/creating
              className="text-muted-foreground hover:text-destructive" // Style for delete
              title="Delete this chat"
            >
              {isDeletingChat ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
              <span className="sr-only">Delete Chat</span>
            </Button>
          )}
        </div>
        <ScrollArea className="flex-1 p-4 min-h-0" id="message-scroll-area">
          <div className="space-y-4">
            {/* Only show full loading indicator on initial load/switch, not during send/reply */}
            {isFetchingMessages && !isLoading && currentMessages.length === 0 && (
              <div className="flex justify-center items-center p-4">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                <span className="ml-2 text-muted-foreground">Loading messages...</span>
              </div>
            )}
            {/* Render messages if not doing an initial fetch OR if we are loading but already have messages (optimistic update) */}
            {(!isFetchingMessages || currentMessages.length > 0) && currentMessages.map((message) => (
              <div
                // Use Firestore message ID for the key - this is crucial for React updates
                key={message.id}
                className={`flex ${
                  message.sender === "user" ? "justify-end" : "justify-start"
                }`}
              >
                <div
                  className={`max-w-[75%] rounded-lg px-4 py-2 ${
                    message.sender === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted"
                  }`}
                >
                  {/* Use ReactMarkdown for bot messages, plain text for user */}
                  {message.sender === "bot" ? (
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm, remarkBreaks]}
                      components={{
                        // Customize rendering if needed
                        p: ({ node, ...props }) => <p className="mb-0" {...props} />, // Remove default margins
                      }}
                    >
                      {message.text}
                    </ReactMarkdown>
                  ) : (
                    message.text // Render user text directly
                  )}
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
              disabled={isLoading || isFetchingMessages || isFetchingChats || isCreatingChat || isDeletingChat || !activeChatId} // <-- Disable during delete
            />
            <Button
              type="submit" // Can be submit if wrapped in a form, or just button
              size="icon"
              className="absolute right-2 top-1/2 -translate-y-1/2 h-8 w-8"
              onClick={handleSendMessage}
              disabled={isLoading || isFetchingMessages || isFetchingChats || isCreatingChat || isDeletingChat || !activeChatId || !inputValue.trim()} // <-- Disable during delete
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
