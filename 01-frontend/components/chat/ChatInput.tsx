"use client";

import React, { useRef, useEffect } from 'react';
import { Play, ChevronDown, Check } from 'lucide-react';
import * as Select from '@radix-ui/react-select';

interface ChatInputProps {
  inputValue: string;
  setInputValue: (value: string) => void;
  handleSendMessage: () => void;
  handleStopGeneration: () => void;
  isLoading: boolean;
  isGenerating: boolean;
  interactionDisabled: boolean;
  activeChatId: string | null;
  activeTypingMessageId: string | null;
  selectedModel: string;
  setSelectedModel: React.Dispatch<React.SetStateAction<string>>;
}

export function ChatInput({
  inputValue,
  setInputValue,
  handleSendMessage,
  handleStopGeneration,
  isLoading,
  isGenerating,
  interactionDisabled,
  activeChatId,
  activeTypingMessageId,
  selectedModel,
  setSelectedModel,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Adjust textarea height whenever the value changes (also collapses when cleared)
  useEffect(() => {
    if (textareaRef.current) {
      const el = textareaRef.current;
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 200) + "px";
    }
  }, [inputValue]);

  return (
    <div className="sticky bottom-0">
      <div className="max-w-[768px] mx-auto pt-0 pb-4 px-4 bg-transparent">
        <div className="bg-[#353535] rounded-md border border-chatgpt-border px-4 py-2 relative">
          {/* Toolbar */}
          <div className="flex items-center justify-between pb-1 mb-2 -mx-4 px-4 border-b border-chatgpt-border">
            {/* Play / Run cell button */}
            <button
              className={`w-6 h-6 flex items-center justify-center transition-colors ${
                inputValue.trim() && !interactionDisabled && activeChatId
                  ? "text-white hover:text-chatgpt-secondary cursor-pointer"
                  : "text-[#4D4D5F] cursor-not-allowed"
              }`}
              onClick={handleSendMessage}
              disabled={interactionDisabled || !activeChatId || !inputValue.trim()}
              title="Run cell"
            >
              <Play className="w-4 h-4" strokeWidth={2} fill="currentColor" />
            </button>

            {/* Model selector */}
            <Select.Root value={selectedModel} onValueChange={setSelectedModel} disabled={interactionDisabled}>
              <Select.Trigger className="flex items-center gap-1 text-chatgpt text-xs focus:outline-none cursor-pointer" aria-label="Model selector">
                <Select.Value />
                <Select.Icon asChild>
                  <ChevronDown className="w-3 h-3" />
                </Select.Icon>
              </Select.Trigger>
              <Select.Portal>
                <Select.Content className="bg-chatgpt-sidebar text-chatgpt border border-chatgpt-border rounded-md shadow-lg overflow-hidden">
                  <Select.Viewport className="py-1">
                    {['Gemini 2.5 Pro', 'Gemini 2.5 Flash', 'Gemini 2.5 Flash Lite'].map((model) => (
                      <Select.Item
                        key={model}
                        value={model}
                        className="cursor-pointer px-3 py-1 text-xs flex items-center gap-2 outline-none data-[highlighted]:bg-chatgpt-hover"
                      >
                        <Select.ItemText>{model}</Select.ItemText>
                        <Select.ItemIndicator className="ml-auto">
                          <Check className="w-3 h-3" />
                        </Select.ItemIndicator>
                      </Select.Item>
                    ))}
                  </Select.Viewport>
                </Select.Content>
              </Select.Portal>
            </Select.Root>
          </div>

          {/* Center - Textarea */}
          <div>
            <textarea
              placeholder="Write a message …"
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
                  if (!activeTypingMessageId && inputValue.trim()) {
                    handleSendMessage();
                  }
                }
              }}
              disabled={interactionDisabled || !activeChatId}
              rows={1}
              ref={textareaRef}
            />
          </div>

          {/* Bottom action buttons removed for notebook-style layout */}
        </div>
      </div>
    </div>
  );
} 