import React, { forwardRef, useImperativeHandle, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';

export interface ChatSidebarHandle {
  sendMessage: (text: string) => void;
  toggle: () => void;
}

type Message = { id: string; text: string; sender: 'user' | 'bot' };

const ChatSidebar = forwardRef<ChatSidebarHandle>((_, ref) => {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [chatId, setChatId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const sendMessage = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;

    const optimistic: Message = {
      id: `temp-${Date.now()}`,
      text: trimmed,
      sender: 'user',
    };

    setMessages((prev) => [...prev, optimistic]);
    setIsOpen(true);
    setIsLoading(true);

    let currentChatId = chatId;
    try {
      if (!currentChatId) {
        const res = await fetch('/api/chats', { method: 'POST' });
        if (!res.ok) throw new Error('Failed to create chat');
        const data = await res.json();
        currentChatId = data.id;
        setChatId(currentChatId);
      }

      const res = await fetch(`/api/chats/${currentChatId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: trimmed }),
      });
      if (!res.ok) throw new Error('Failed to send message');
      const { user_message, bot_message } = await res.json();

      setMessages((prev) => [
        ...prev.filter((m) => m.id !== optimistic.id),
        user_message,
        bot_message,
      ]);
    } catch (err) {
      console.error('Error sending message:', err);
      setMessages((prev) => [
        ...prev.filter((m) => m.id !== optimistic.id),
        { id: `err-${Date.now()}`, text: 'Error getting reply', sender: 'bot' },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const toggle = () => {
    setIsOpen((prev) => !prev);
  };

  useImperativeHandle(ref, () => ({ sendMessage, toggle }));

  return (
    <>
      <div
        className={`fixed top-14 right-0 h-[calc(100vh-theme(spacing.14))] w-80 bg-background border-l shadow-lg transition-transform ${isOpen ? 'translate-x-0' : 'translate-x-full'}`}
      >
        <ScrollArea className="h-full p-4 space-y-2">
          {messages.map((m) => (
            <div
              key={m.id}
              className={`text-sm ${m.sender === 'user' ? 'text-right' : 'text-left'}`}
            >
              <div
                className={`inline-block px-3 py-2 rounded-lg ${m.sender === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted'}`}
              >
                {m.text}
              </div>
            </div>
          ))}
          {isLoading && (
            <div className="flex items-center space-x-2 text-sm text-muted-foreground">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Thinking...</span>
            </div>
          )}
        </ScrollArea>
      </div>
      <button
        onClick={() => setIsOpen((o) => !o)}
        className={`fixed top-1/2 transform -translate-y-1/2 bg-background border border-r-0 rounded-l-md px-3 py-2 text-sm shadow-lg hover:bg-muted transition-all duration-200 z-50 ${
          isOpen 
            ? 'right-80 border-l' 
            : 'right-0 border-l-0'
        }`}
      >
        {isOpen ? '→' : '←'}
      </button>
    </>
  );
});

ChatSidebar.displayName = 'ChatSidebar';
export default ChatSidebar;
