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
import { Loader2, Trash2, LogOut, LogIn } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { useSession, signOut, signIn } from "next-auth/react";
import { authFetch } from "@/lib/authFetch";
import Link from "next/link";

/* -------------------------------------------------------------------------- */
/*                                   Types                                    */
/* -------------------------------------------------------------------------- */

type Sender = "user" | "bot";

type Message = {
  id: string;
  text: string;
  sender: Sender;
  timestamp: string;
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

const CHATS_ENDPOINT = '/api/chats';
const getMessagesEndpoint = (chatId: string) => `${CHATS_ENDPOINT}/${chatId}/messages`;
const postMessageEndpoint = (chatId: string) => `${CHATS_ENDPOINT}/${chatId}/messages`;
const deleteChatEndpoint = (chatId: string) => `${CHATS_ENDPOINT}/${chatId}`;

/* -------------------------------------------------------------------------- */
/*                               Main Component                               */
/* -------------------------------------------------------------------------- */

export default function HomePage() {
  const { data: session } = useSession();
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
        const res = await authFetch(session, getMessagesEndpoint(chatId));

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
    [clearTypingEffect, session],
  );

  /* --------------------------- Initial Load ------------------------------- */

  useEffect(() => {
    const loadInitialChats = async () => {
      clearTypingEffect();
      activeTypingMessageId.current = null;
      setIsFetchingChats(true);

      try {
        const res = await authFetch(session, CHATS_ENDPOINT);
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

    if (session) {
      loadInitialChats();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]);

  /* ------------------------------------------------------------------------ */
  /*                            Chat Operations                               */
  /* ------------------------------------------------------------------------ */

  const handleNewChat = useCallback(async () => {
    clearTypingEffect();
    activeTypingMessageId.current = null;
    setIsCreatingChat(true);

    try {
      const res = await authFetch(session, CHATS_ENDPOINT, { method: "POST" });
      if (!res.ok) throw new Error(`Failed to create chat: ${res.statusText}`);

      const {
        id,
        title,
        messages,
      }: { id: string; title: string; messages?: Message[] } = await res.json();

      const newMeta: ChatMetadata = {
        id,
        title,
        lastActivity: new Date().toISOString(),
      };

      setChatList((prev) => [newMeta, ...prev]);
      setActiveChatId(id);
      setCurrentMessages(messages || []);
      setInputValue("");
      scrollToBottom("instant");
    } catch (err) {
      console.error("Error creating new chat:", err);
    } finally {
      setIsCreatingChat(false);
    }
  }, [clearTypingEffect, session]);

  const handleSelectChat = (chatId: string) => {
    if (chatId === activeChatId || isDeletingChat) return;

    clearTypingEffect();
    activeTypingMessageId.current = null;
    setActiveChatId(chatId);
    fetchMessages(chatId);
  };

  const handleDeleteChat = async (chatId: string) => {
    if (!chatId || isDeletingChat) return;

    if (activeTypingMessageId.current && chatId === activeChatId) {
      clearTypingEffect();
      activeTypingMessageId.current = null;
    }

    setIsDeletingChat(true);
    try {
      const res = await authFetch(session, deleteChatEndpoint(chatId), { method: "DELETE" });

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
      const res = await authFetch(session, postMessageEndpoint(activeChatId), {
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
    <div className="flex h-screen w-full overflow-hidden bg-chatgpt-main">
      {/* ------------------------------ Sidebar ----------------------------- */}
      <aside className="chatgpt-sidebar flex flex-col border-r border-chatgpt">
        {/* Header Controls */}
        <div className="p-3 space-y-3">
          {/* Navigation Links */}
          <div className="flex flex-col gap-1 mb-2">
            <button
              onClick={handleNewChat}
              disabled={interactionDisabled}
              className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-chatgpt hover:bg-chatgpt-hover rounded-lg transition-colors disabled:cursor-not-allowed"
            >
              {isCreatingChat && <Loader2 className="h-4 w-4 animate-spin" />}
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              New Chat
            </button>
            <Link
              href="/knowledge-base"
              className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-chatgpt hover:bg-chatgpt-hover rounded-lg transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
              Upload
            </Link>
          </div>

        </div>

        {/* Chats Header */}
        <div className="px-3 py-2">
          <h3 className="text-sm text-chatgpt-secondary font-normal">Chats</h3>
        </div>

        {/* Conversation List */}
        <div className="flex-1 overflow-hidden">
          <ScrollArea className="h-full px-2">
            {isFetchingChats ? (
              <div className="p-4 text-center text-chatgpt-secondary text-sm">
                Loading chats...
              </div>
            ) : (
              <div className="space-y-0.5 pb-4">
                {chatList.map((chat) => (
                  <button
                    key={chat.id}
                    className={`w-full text-left px-3 h-[34px] flex items-center cursor-pointer disabled:cursor-not-allowed rounded-lg text-sm font-normal transition-all relative group ${
                      chat.id === activeChatId
                        ? "bg-chatgpt-hover text-chatgpt"
                        : "text-chatgpt hover:bg-chatgpt-hover"
                    }`}
                    onClick={() => handleSelectChat(chat.id)}
                    disabled={interactionDisabled}
                  >
                    <div className="flex-1 flex items-center min-w-0">
                      <span className="truncate flex-1">{chat.title}</span>
                    </div>
                    
                    {/* Delete button - shows on hover */}
                    <button
                      className="opacity-0 group-hover:opacity-100 flex-shrink-0 ml-2 p-1 hover:bg-red-600/20 rounded transition-all"
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
                  </button>
                ))}
              </div>
            )}
          </ScrollArea>
        </div>


      </aside>

      {/* --------------------------- Main Chat ----------------------------- */}
      <main className="flex-1 flex flex-col overflow-hidden bg-chatgpt-main relative">
        {/* User Icon - Top Right */}
        <div className="absolute top-4 right-4 z-10">
          {session?.user ? (
            <button
              onClick={() => signOut()}
              className="w-8 h-8 bg-chatgpt-accent rounded-full flex items-center justify-center text-sm font-medium text-white hover:opacity-80 transition-opacity"
              title={`${session.user.name ?? session.user.email} - Click to sign out`}
            >
              {session.user.name?.charAt(0) || session.user.email?.charAt(0) || "U"}
            </button>
          ) : (
            <button
              onClick={() => signIn("google", { callbackUrl: "/" })}
              className="w-8 h-8 bg-chatgpt-accent rounded-full flex items-center justify-center text-sm font-medium text-white hover:opacity-80 transition-opacity"
              title="Sign in"
            >
              <LogIn className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* -------------------------- Messages ------------------------------ */}
        <ScrollArea className="flex-1 min-h-0" id="message-scroll-area">
          <div className="w-full">
            <div className="max-w-[720px] mx-auto px-4 py-5 space-y-6">
              {isFetchingMessages && !currentMessages.length && (
                <div className="flex justify-center items-center p-4">
                  <Loader2 className="h-6 w-6 animate-spin text-chatgpt-secondary" />
                  <span className="ml-2 text-chatgpt-secondary text-sm">
                    Loading messages...
                  </span>
                </div>
              )}

              {currentMessages.map((m) => (
                <div
                  key={m.id}
                  className="w-full"
                >
                  {m.sender === "user" ? (
                    /* User Message - Right-aligned bubble */
                    <div className="flex justify-end">
                      <div className="chatgpt-user-bubble px-4 py-3 rounded-lg rounded-br-none max-w-[70%]">
                        <div className="text-sm leading-relaxed whitespace-pre-wrap">{m.text}</div>
                      </div>
                    </div>
                  ) : (
                    /* Assistant Message - Left-aligned, transparent bg */
                    <div className="flex justify-start">
                      <div className="max-w-[70%] px-4 py-3">
                        <div className="prose prose-invert text-chatgpt text-sm leading-relaxed max-w-none">
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm, remarkBreaks]}
                            rehypePlugins={[rehypeRaw]}
                            components={{
                              p: ({ ...props }) => (
                                <p className="mb-4 last:mb-0 leading-relaxed" {...props} />
                              ),
                              ul: ({ ...props }) => (
                                <ul className="mb-4 last:mb-0 list-disc list-outside ml-6 space-y-1" {...props} />
                              ),
                              ol: ({ ...props }) => (
                                <ol className="mb-4 last:mb-0 list-decimal list-outside ml-6 space-y-1" {...props} />
                              ),
                              li: ({ ...props }) => (
                                <li className="leading-relaxed" style={{ color: '#ECECF1' }} {...props} />
                              ),
                              code: ({ className, children, ...props }) => {
                                const isInline = !className?.includes('language-');
                                if (isInline) {
                                  return (
                                    <code 
                                      className="bg-[#202123] px-1.5 py-0.5 rounded text-xs font-mono text-chatgpt" 
                                      style={{ fontFamily: 'SFMono-Regular, Consolas, Liberation Mono, Menlo, monospace' }}
                                      {...props}
                                    >
                                      {children}
                                    </code>
                                  );
                                }
                                return (
                                  <code 
                                    className={className} 
                                    style={{ fontFamily: 'SFMono-Regular, Consolas, Liberation Mono, Menlo, monospace' }}
                                    {...props}
                                  >
                                    {children}
                                  </code>
                                );
                              },
                              pre: ({ children, ...props }) => (
                                <pre 
                                  className="bg-[#202123] p-3 rounded overflow-x-auto text-xs text-chatgpt mb-4 last:mb-0" 
                                  style={{ fontFamily: 'SFMono-Regular, Consolas, Liberation Mono, Menlo, monospace', fontSize: '12px' }}
                                  {...props}
                                >
                                  {children}
                                </pre>
                              ),
                              blockquote: ({ ...props }) => (
                                <blockquote className="border-l-4 border-chatgpt-border pl-4 mb-4 last:mb-0 italic text-chatgpt-secondary" {...props} />
                              ),
                              h1: ({ ...props }) => (
                                <h1 className="text-lg font-semibold mb-3 text-chatgpt" {...props} />
                              ),
                              h2: ({ ...props }) => (
                                <h2 className="text-base font-semibold mb-3 text-chatgpt" {...props} />
                              ),
                              h3: ({ ...props }) => (
                                <h3 className="text-sm font-semibold mb-2 text-chatgpt" {...props} />
                              ),
                              strong: ({ ...props }) => (
                                <strong className="font-semibold text-chatgpt" {...props} />
                              ),
                              em: ({ ...props }) => (
                                <em className="italic text-chatgpt" {...props} />
                              ),
                              a: ({ ...props }) => (
                                <a className="text-blue-400 hover:text-blue-300 underline" {...props} />
                              ),
                              table: ({ ...props }) => (
                                <div className="overflow-x-auto mb-4 last:mb-0">
                                  <table className="min-w-full border-collapse border border-chatgpt-border" {...props} />
                                </div>
                              ),
                              th: ({ ...props }) => (
                                <th className="border border-chatgpt-border px-3 py-2 bg-chatgpt-input text-left font-medium" {...props} />
                              ),
                              td: ({ ...props }) => (
                                <td className="border border-chatgpt-border px-3 py-2" {...props} />
                              ),
                            }}
                          >
                            {m.text || ""}
                          </ReactMarkdown>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ))}

              {isLoading && (
                <div className="flex justify-start">
                  <div className="px-4 py-3">
                    <div className="flex items-center space-x-2 text-chatgpt-secondary text-sm">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span>Thinking...</span>
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          </div>
        </ScrollArea>

        {/* -------------------------- Input --------------------------------- */}
        <div className="sticky bottom-0 bg-chatgpt-main">
          <div className="max-w-[768px] mx-auto p-4">
            <div className="bg-[#2F2F2F] rounded-3xl px-4 py-4 relative">
              {/* Center - Textarea */}
              <div className="pb-10">
                <textarea
                  placeholder="Message ChatGPT..."
                  className="w-full min-h-[32px] max-h-[200px] bg-transparent border-0 text-sm text-chatgpt resize-none focus:outline-none leading-6 chatgpt-textarea placeholder:text-chatgpt-secondary"
                  value={inputValue}
                  onChange={(e) => {
                    setInputValue(e.target.value);
                    // Auto-resize textarea
                    e.target.style.height = 'auto';
                    e.target.style.height = Math.min(e.target.scrollHeight, 200) + 'px';
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      if (!activeTypingMessageId.current && inputValue.trim()) {
                        handleSendMessage();
                      }
                    }
                  }}
                  disabled={interactionDisabled || !activeChatId}
                  rows={1}
                />
              </div>

              {/* Bottom row - Buttons */}
              <div className="absolute bottom-4 left-4 right-4 flex justify-between items-center">
                {/* Left side - Attach button */}
                <button
                  className="w-8 h-8 flex items-center justify-center rounded-full text-chatgpt-secondary hover:text-chatgpt hover:bg-chatgpt-hover transition-colors"
                  title="Attach files"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                </button>

                {/* Right side - Action buttons */}
                <div className="flex items-center gap-2">
                  {/* Microphone Button */}
                  <button
                    className="w-8 h-8 flex items-center justify-center rounded-full text-chatgpt-secondary hover:text-chatgpt hover:bg-chatgpt-hover transition-colors"
                    title="Voice input"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                    </svg>
                  </button>

                  {/* Send Button */}
                  <button
                    className={`w-8 h-8 rounded-full flex items-center justify-center transition-all ${
                      inputValue.trim() && !interactionDisabled && activeChatId
                        ? "bg-white text-black hover:bg-gray-200 cursor-pointer"
                        : "bg-[#676767] text-[#2F2F2F] cursor-not-allowed"
                    }`}
                    onClick={handleSendMessage}
                    disabled={
                      interactionDisabled ||
                      !activeChatId ||
                      !inputValue.trim()
                    }
                    title="Send message"
                  >
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M12 4l6 6h-4v10h-4V10H6l6-6z" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
