"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useSession } from 'next-auth/react';
import { authFetch } from '@/lib/authFetch';
import { Message, ChatMetadata } from '@/types';
import {
  CHATS_ENDPOINT,
  getMessagesEndpoint,
  postMessageEndpoint,
  deleteChatEndpoint,
  MAX_TITLE_LENGTH,
  TYPING_INTERVAL_MS,
} from '@/lib/constants';

export const useChat = () => {
  const { data: session } = useSession();
  const [inputValue, setInputValue] = useState("");

  const [chatList, setChatList] = useState<ChatMetadata[]>([]);
  const [currentMessages, setCurrentMessages] = useState<Message[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);

  const [isLoading, setIsLoading] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isFetchingChats, setIsFetchingChats] = useState(true);
  const [isFetchingMessages, setIsFetchingMessages] = useState(false);
  const [isCreatingChat, setIsCreatingChat] = useState(false);
  const [isDeletingChat, setIsDeletingChat] = useState(false);

  const typingTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const activeTypingMessageId = useRef<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const interactionDisabled = useMemo(
    () =>
      isLoading ||
      isGenerating ||
      isFetchingMessages ||
      isFetchingChats ||
      isCreatingChat ||
      isDeletingChat,
    [
      isLoading,
      isGenerating,
      isFetchingMessages,
      isFetchingChats,
      isCreatingChat,
      isDeletingChat,
    ],
  );

  const clearTypingEffect = useCallback(() => {
    if (typingTimeoutRef.current) {
      clearTimeout(typingTimeoutRef.current);
      typingTimeoutRef.current = null;
    }
  }, []);

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
    } catch (err) {
      console.error("Error creating new chat:", err);
    } finally {
      setIsCreatingChat(false);
    }
  }, [clearTypingEffect, session]);

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
            if (chatList.length === 1) { // If it was the last chat
              await handleNewChat();
            }
            return;
          }
          throw new Error(`Failed to fetch messages: ${res.statusText}`);
        }

        const data: Message[] = await res.json();
        data.sort(
          (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
        );
        setCurrentMessages(data);
      } catch (err) {
        if (!(err instanceof Error && err.message.includes("404"))) {
          console.error("Error fetching messages:", err);
        }
      } finally {
        setIsFetchingMessages(false);
      }
    },
    [clearTypingEffect, session, handleNewChat, chatList],
  );

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


  const handleSelectChat = (chatId: string) => {
    if (chatId === activeChatId || isDeletingChat) return;

    clearTypingEffect();
    activeTypingMessageId.current = null;
    setActiveChatId(chatId);
    fetchMessages(chatId);
  };

  const handleDeleteChat = async (chatId: string) => {
    if (isDeletingChat) return;

    setIsDeletingChat(true);

    try {
      const res = await authFetch(session, deleteChatEndpoint(chatId), {
        method: "DELETE",
      });
      if (!res.ok) throw new Error(`Failed to delete chat: ${res.statusText}`);
        
      const newChatList = chatList.filter((c) => c.id !== chatId)
      setChatList(newChatList);

      if (chatId === activeChatId) {
        if (newChatList.length > 0) {
          const newActiveId = newChatList[0].id
          setActiveChatId(newActiveId);
          await fetchMessages(newActiveId);
        } else {
          await handleNewChat();
        }
      }
    } catch (err) {
      console.error("Error deleting chat:", err);
    } finally {
      setIsDeletingChat(false);
    }
  };

  const startTypingEffect = useCallback(
    (messageId: string, fullText: string) => {
      clearTypingEffect();
      activeTypingMessageId.current = messageId;
      setIsGenerating(true);

      let idx = 0;
      const typeStep = () => {
        if (activeTypingMessageId.current !== messageId) return;

        idx += 1;
        setCurrentMessages((prev) =>
          prev.map((m) =>
            m.id === messageId ? { ...m, text: fullText.slice(0, idx) } : m,
          ),
        );

        if (idx < fullText.length) {
          typingTimeoutRef.current = setTimeout(typeStep, TYPING_INTERVAL_MS);
        } else {
          activeTypingMessageId.current = null;
          typingTimeoutRef.current = null;
          setIsGenerating(false);
        }
      };

      typingTimeoutRef.current = setTimeout(typeStep, TYPING_INTERVAL_MS);
    },
    [clearTypingEffect],
  );

  const handleStopGeneration = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    clearTypingEffect();
    activeTypingMessageId.current = null;
    setIsLoading(false);
    setIsGenerating(false);
  }, [clearTypingEffect]);

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

    setIsLoading(true);

    try {
      const abortController = new AbortController();
      abortControllerRef.current = abortController;

      const res = await authFetch(session, postMessageEndpoint(activeChatId), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: trimmed }),
        signal: abortController.signal,
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

      setTimeout(() => startTypingEffect(bot_message.id, bot_message.text), 50);

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
      if (err instanceof Error && err.name === 'AbortError') {
        console.log("Message generation stopped by user");
        setCurrentMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
      } else {
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
      }
      setIsLoading(false);
    } finally {
      abortControllerRef.current = null;
    }
  };

  return {
    session,
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
    activeTypingMessageId: activeTypingMessageId.current
  };
}; 