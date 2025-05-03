"use client";

import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
  useMemo,
  KeyboardEvent,
} from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Loader2, Trash2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";

/* -------------------------------------------------------------------------- */
/*                                   Types                                    */
/* -------------------------------------------------------------------------- */

type Sender = "user" | "bot";

type DocSource = { id: string; name: string; uri?: string };

type Message = {
  id: string;
  text: string;
  sender: Sender;
  timestamp: string;
  sources?: DocSource[];
};

type ChatMetadata = {
  id: string;
  title: string;
  lastActivity: string;
};

/* -------------------------------------------------------------------------- */
/*                                Const Values                                */
/* -------------------------------------------------------------------------- */

const MAX_TITLE_LENGTH = 30;
const TYPING_INTERVAL_MS = 3;

const BACKEND_API_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8080";

const CHATS_ENDPOINT = `${BACKEND_API_URL}/chats`;
const getMessagesEndpoint = (chatId: string) =>
  `${CHATS_ENDPOINT}/${chatId}/messages`;
const postMessageEndpoint = (chatId: string) =>
  `${BACKEND_API_URL}/chat/${chatId}`;
const deleteChatEndpoint = (chatId: string) => `${CHATS_ENDPOINT}/${chatId}`;

/* -------------------------------------------------------------------------- */
/*                               Main Component                               */
/* -------------------------------------------------------------------------- */

export default function ChatPage() {
  /* ------------------------------- State ---------------------------------- */
  const [inputValue, setInputValue] = useState("");

  const [chatList, setChatList] = useState<ChatMetadata[]>([]);
  const [currentMessages, setCurrentMessages] = useState<Message[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);

  const [isLoading, setIsLoading] = useState(false);
  const [isFetchingChats, setIsFetchingChats] = useState(true);
  const [isFetchingMessages, setIsFetchingMessages] = useState(false);
  const [isCreatingChat, setIsCreatingChat] = useState(false);
  const [isDeletingChat, setIsDeletingChat] = useState(false);

  /* ------------------------------ Refs ------------------------------------ */
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const typingTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const activeTypingMessageId = useRef<string | null>(null);

  /* ------------------------- Derived Booleans ----------------------------- */
  const interactionDisabled = useMemo(
    () =>
      isLoading ||
      isFetchingMessages ||
      isFetchingChats ||
      isCreatingChat ||
      isDeletingChat ||
      !!activeTypingMessageId.current,
    [
      isLoading,
      isFetchingMessages,
      isFetchingChats,
      isCreatingChat,
      isDeletingChat,
    ],
  );

  /* ------------------------------------------------------------------------ */
  /*                               Utilities                                  */
  /* ------------------------------------------------------------------------ */

  const scrollToBottom = (behavior: ScrollBehavior = "smooth") => {
    requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({ behavior });
    });
  };

  const clearTypingEffect = useCallback(() => {
    if (typingTimeoutRef.current) {
      clearTimeout(typingTimeoutRef.current);
      typingTimeoutRef.current = null;
    }
  }, []);

  /* ------------------------------------------------------------------------ */
  /*                             Data Fetching                                */
  /* ------------------------------------------------------------------------ */

  const fetchMessages = useCallback(
    async (chatId: string) => {
      if (!chatId) return;

      clearTypingEffect();
      activeTypingMessageId.current = null;
      setIsFetchingMessages(true);
      setCurrentMessages([]);

      try {
        const res = await fetch(getMessagesEndpoint(chatId));

        if (!res.ok) {
          if (res.status === 404) {
            setChatList((prev) => prev.filter((c) => c.id !== chatId));
            setActiveChatId(null);
            return;
          }
          throw new Error(`Failed to fetch messages: ${res.statusText}`);
        }

        const data: Message[] = await res.json();
        data.sort(
          (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
        );
        setCurrentMessages(data);
        scrollToBottom("instant");
      } catch (err) {
        if (!(err instanceof Error && err.message.includes("404"))) {
          console.error("Error fetching messages:", err);
        }
      } finally {
        setIsFetchingMessages(false);
      }
    },
    [clearTypingEffect],
  );

  /* --------------------------- Initial Load ------------------------------- */

  useEffect(() => {
    const loadInitialChats = async () => {
      clearTypingEffect();
      activeTypingMessageId.current = null;
      setIsFetchingChats(true);

      try {
        const res = await fetch(CHATS_ENDPOINT);
        if (!res.ok) throw new Error(`Failed to fetch chats: ${res.statusText}`);

        const chats: ChatMetadata[] = await res.json();
        setChatList(chats);

        if (chats.length) {
          setActiveChatId(chats[0].id);
          await fetchMessages(chats[0].id);
        } else {
          await handleNewChat();
        }
      } catch (err) {
        console.error("Error fetching initial chats:", err);
      } finally {
        setIsFetchingChats(false);
      }
    };

    loadInitialChats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchMessages]);

  /* ------------------------------------------------------------------------ */
  /*                            Chat Operations                               */
  /* ------------------------------------------------------------------------ */

  const handleNewChat = useCallback(async () => {
    clearTypingEffect();
    activeTypingMessageId.current = null;
    setIsCreatingChat(true);

    try {
      const res = await fetch(CHATS_ENDPOINT, { method: "POST" });
      if (!res.ok) throw new Error(`Failed to create chat: ${res.statusText}`);

      const {
        id,
        title,
        messages,
      }: { id: string; title: string; messages: Message[] } = await res.json();

      const newMeta: ChatMetadata = {
        id,
        title,
        lastActivity: new Date().toISOString(),
      };

      setChatList((prev) => [newMeta, ...prev]);
      setActiveChatId(id);
      setCurrentMessages(messages);
      setInputValue("");
      scrollToBottom("instant");
    } catch (err) {
      console.error("Error creating new chat:", err);
    } finally {
      setIsCreatingChat(false);
    }
  }, [clearTypingEffect]);

  const handleSelectChat = (chatId: string) => {
    if (chatId === activeChatId || isDeletingChat) return;

    clearTypingEffect();
    activeTypingMessageId.current = null;
    setActiveChatId(chatId);
    fetchMessages(chatId);
  };

  const handleDeleteChat = async (chatId: string) => {
    if (!chatId || isDeletingChat) return;

    if (
      !window.confirm(
        "Are you sure you want to delete this chat and all its messages?",
      )
    )
      return;

    if (activeTypingMessageId.current && chatId === activeChatId) {
      clearTypingEffect();
      activeTypingMessageId.current = null;
    }

    setIsDeletingChat(true);
    try {
      const res = await fetch(deleteChatEndpoint(chatId), { method: "DELETE" });

      if (!res.ok) {
        const errText = await res.text();
        throw new Error(`Failed to delete chat: ${errText || res.statusText}`);
      }

      const remaining = chatList.filter((c) => c.id !== chatId);
      setChatList(remaining);

      if (activeChatId === chatId) {
        if (remaining.length) {
          setActiveChatId(remaining[0].id);
          await fetchMessages(remaining[0].id);
        } else {
          setActiveChatId(null);
          setCurrentMessages([]);
          await handleNewChat();
        }
      }
    } catch (err) {
      console.error("Error deleting chat:", err);
      alert(
        `Failed to delete chat: ${err instanceof Error ? err.message : "Unknown"}`,
      );
    } finally {
      setIsDeletingChat(false);
    }
  };

  /* ------------------------------------------------------------------------ */
  /*                             Message Send                                 */
  /* ------------------------------------------------------------------------ */

  const startTypingEffect = useCallback(
    (messageId: string, fullText: string) => {
      clearTypingEffect();
      activeTypingMessageId.current = messageId;

      let idx = 0;
      const typeStep = () => {
        if (activeTypingMessageId.current !== messageId) return;

        idx += 1;
        setCurrentMessages((prev) =>
          prev.map((m) =>
            m.id === messageId ? { ...m, text: fullText.slice(0, idx) } : m,
          ),
        );
        scrollToBottom("smooth");

        if (idx < fullText.length) {
          typingTimeoutRef.current = setTimeout(typeStep, TYPING_INTERVAL_MS);
        } else {
          activeTypingMessageId.current = null;
          typingTimeoutRef.current = null;
          scrollToBottom("smooth");
        }
      };

      typingTimeoutRef.current = setTimeout(typeStep, TYPING_INTERVAL_MS);
    },
    [clearTypingEffect],
  );

  const handleSendMessage = async () => {
    const trimmed = inputValue.trim();
    if (!activeChatId || !trimmed || interactionDisabled) return;

    setInputValue("");

    const optimistic: Message = {
      id: `temp-${Date.now()}`,
      text: trimmed,
      sender: "user",
      timestamp: new Date().toISOString(),
    };

    setCurrentMessages((prev) => [...prev, optimistic]);
    scrollToBottom();

    setIsLoading(true);

    try {
      const res = await fetch(postMessageEndpoint(activeChatId), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: trimmed }),
      });

      if (!res.ok) {
        const err = await res.text();
        throw new Error(`Backend query failed: ${err || res.statusText}`);
      }

      const {
        user_message,
        bot_message,
      }: { user_message: Message; bot_message: Message } = await res.json();

      const placeholder: Message = { ...bot_message, text: "" };

      setIsLoading(false);
      setCurrentMessages((prev) => [
        ...prev.filter((m) => m.id !== optimistic.id),
        user_message,
        placeholder,
      ]);
      scrollToBottom();

      setTimeout(() => startTypingEffect(bot_message.id, bot_message.text), 50);

      /* ---------------------- Chat list metadata -------------------------- */
      setChatList((prev) => {
        const idx = prev.findIndex((c) => c.id === activeChatId);
        if (idx === -1) return prev;

        const updated = { ...prev[idx] };
        updated.lastActivity = bot_message.timestamp;
        if (updated.title === "New Chat") {
          const newTitle =
            user_message.text.slice(0, MAX_TITLE_LENGTH) +
            (user_message.text.length > MAX_TITLE_LENGTH ? "..." : "");
          updated.title = newTitle;
        }
        return [updated, ...prev.slice(0, idx), ...prev.slice(idx + 1)];
      });
    } catch (err) {
      console.error("Failed to send message:", err);

      const errorMsg: Message = {
        id: `error-${Date.now()}`,
        text: `Sorry, failed to process message. ${
          err instanceof Error ? err.message : ""
        }`,
        sender: "bot",
        timestamp: new Date().toISOString(),
      };

      setCurrentMessages((prev) => [
        ...prev.filter((m) => m.id !== optimistic.id),
        errorMsg,
      ]);
      scrollToBottom();
      setIsLoading(false);
    }
  };

  /* ------------------------------------------------------------------------ */
  /*                             Event Helpers                                */
  /* ------------------------------------------------------------------------ */

  const handleKeyPress = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!activeTypingMessageId.current) handleSendMessage();
    }
  };

  const activeChatTitle =
    chatList.find((c) => c.id === activeChatId)?.title ?? "Chat";

  /* ------------------------------------------------------------------------ */
  /*                                 Render                                   */
  /* ------------------------------------------------------------------------ */

  return (
    <div className="flex h-[calc(100vh-theme(spacing.14)-theme(spacing.6))] border rounded-lg overflow-hidden">
      {/* ------------------------------ Sidebar ----------------------------- */}
      <aside className="w-64 md:w-72 border-r flex flex-col bg-muted/30">
        <div className="p-4 border-b">
          <h2 className="text-lg font-semibold tracking-tight">Recent Chats</h2>
        </div>

        <ScrollArea className="flex-1 p-2 min-h-0">
          {isFetchingChats ? (
            <div className="p-4 text-center text-muted-foreground">
              Loading chats...
            </div>
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
                  } hover:cursor-pointer`}
                  onClick={() => handleSelectChat(chat.id)}
                  disabled={interactionDisabled}
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
            disabled={interactionDisabled}
          >
            {isCreatingChat && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            New Chat
          </Button>
        </div>
      </aside>

      {/* --------------------------- Main  Chat ----------------------------- */}
      <main className="flex-1 flex flex-col overflow-hidden">
        <div className="p-4 border-b flex items-center justify-between bg-background/95">
          <h1 className="text-xl font-bold tracking-tight truncate mr-2">
            {activeChatTitle}
          </h1>

          {activeChatId && (
            <Button
              variant="ghost"
              size="icon"
              onClick={() => handleDeleteChat(activeChatId)}
              disabled={interactionDisabled}
              className="text-muted-foreground hover:text-destructive hover:cursor-pointer disabled:cursor-not-allowed"
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

        {/* -------------------------- Messages ------------------------------ */}
        <ScrollArea className="flex-1 p-4 min-h-0" id="message-scroll-area">
          <div className="space-y-4">
            {isFetchingMessages && !currentMessages.length && (
              <div className="flex justify-center items-center p-4">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                <span className="ml-2 text-muted-foreground">
                  Loading messages...
                </span>
              </div>
            )}

            {currentMessages.map((m) => (
              <div
                key={m.id}
                className={`flex ${
                  m.sender === "user" ? "justify-end" : "justify-start"
                }`}
              >
                <div
                  className={`max-w-[75%] rounded-lg px-4 py-2 ${
                    m.sender === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted message-reveal"
                  }`}
                >
                  {m.sender === "bot" ? (
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm, remarkBreaks]}
                      components={{
                        p: ({ node, ...props }) => <p className="mb-0" {...props} />,
                      }}
                    >
                      {m.text || ""}
                    </ReactMarkdown>
                  ) : (
                    m.text
                  )}

                  {/* ---- Reviewed Documents dropdown ---- */}
                  {m.sender === "bot" && m.sources?.length ? (
                    <details className="mt-2 text-xs">
                      <summary className="cursor-pointer text-muted-foreground">
                        Reviewed Documents ({m.sources.length})
                      </summary>
                      <ul className="ml-4 list-disc">
                        {m.sources.map((s) => (
                          <li key={s.id}>
                            {s.uri ? (
                              <a
                                href={s.uri}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="underline"
                              >
                                {s.name}
                              </a>
                            ) : (
                              s.name
                            )}
                          </li>
                        ))}
                      </ul>
                    </details>
                  ) : null}
                </div>
              </div>
            ))}

            {isLoading && (
              <div className="flex justify-start">
                <div className="p-3 max-w-[75%] text-sm rounded-lg bg-muted flex items-center space-x-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>Thinking...</span>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </ScrollArea>

        {/* -------------------------- Input --------------------------------- */}
        <div className="p-4 border-t bg-background/95">
          <div className="flex items-center gap-2">
            <Input
              type="text"
              placeholder="Type your message..."
              className="flex-1"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyPress={handleKeyPress}
              disabled={interactionDisabled || !activeChatId}
            />

            <Button
              size="icon"
              className="h-9 w-9"
              onClick={handleSendMessage}
              disabled={
                interactionDisabled ||
                !activeChatId ||
                !inputValue.trim()
              }
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="currentColor"
                className="w-5 h-5"
              >
                <path d="M3.478 2.404a.75.75 0 0 0-.926.941l2.432 7.905H13.5a.75.75 0 0 1 0 1.5H4.984l-2.432 7.905a.75.75 0 0 0 .926.94 60.519 60.519 0 0 0 18.445-8.986.75.75 0 0 0 0-1.218A60.517 60.517 0 0 0 3.478 2.404Z" />
              </svg>
              <span className="sr-only">Send</span>
            </Button>
          </div>
        </div>
      </main>
    </div>
  );
}
