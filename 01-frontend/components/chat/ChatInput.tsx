"use client";

import React from 'react';

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
}: ChatInputProps) {
  return (
    <div className="sticky bottom-0">
      <div className="max-w-[768px] mx-auto pt-0 pb-4 px-4 bg-transparent">
        <div className="bg-[#2F2F2F] rounded-3xl px-4 py-4 relative">
          {/* Center - Textarea */}
          <div className="pb-10">
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
              {/* Send/Stop Button */}
              <button
                className={`w-8 h-8 rounded-full flex items-center justify-center transition-all ${
                  (isLoading || isGenerating)
                    ? "bg-white text-black hover:bg-gray-200 cursor-pointer"
                    : inputValue.trim() && !interactionDisabled && activeChatId
                      ? "bg-white text-black hover:bg-gray-200 cursor-pointer"
                      : "bg-[#676767] text-[#2F2F2F] cursor-not-allowed"
                }`}
                onClick={
                  (isLoading || isGenerating)
                    ? handleStopGeneration
                    : handleSendMessage
                }
                disabled={
                  (!isLoading && !isGenerating) &&
                  (interactionDisabled ||
                  !activeChatId ||
                  !inputValue.trim())
                }
                title={
                  (isLoading || isGenerating)
                    ? "Stop generating"
                    : "Send message"
                }
              >
                {(isLoading || isGenerating) ? (
                  /* Stop icon */
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                    <rect x="6" y="6" width="12" height="12" rx="2" />
                  </svg>
                ) : (
                  /* Send icon */
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 19V5m-5 5l5-5 5 5" />
                  </svg>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
} 