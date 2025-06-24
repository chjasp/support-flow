"use client";

import React from 'react';
import { Loader2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkBreaks from 'remark-breaks';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import { Message } from '@/types';

interface MessageListProps {
  messages: Message[];
  isFetchingMessages: boolean;
  isLoading: boolean;
  lastMessageRef: React.Ref<HTMLDivElement>;
  bottomRef: React.Ref<HTMLDivElement>;
  currentThought?: string | null;
}

export function MessageList({
  messages,
  isFetchingMessages,
  isLoading,
  currentThought,
  lastMessageRef,
  bottomRef,
}: MessageListProps) {
  if (isFetchingMessages && !messages.length) {
    return (
      <div className="flex justify-center items-center p-4 h-full">
        <Loader2 className="h-6 w-6 animate-spin text-chatgpt-secondary" />
        <span className="ml-2 text-chatgpt-secondary text-sm">
          Loading messages...
        </span>
      </div>
    );
  }

  // determine last user message index
  let targetIndex = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].sender === 'user') {
      targetIndex = i;
      break;
    }
  }
  if (targetIndex === -1) targetIndex = messages.length - 1; // fallback

  const showThinkingIndicator = isLoading || Boolean(currentThought);

  return (
    <div className="min-h-full flex flex-col [overflow-anchor:none]">
      <div className="w-full max-w-[720px] mx-auto px-4 pt-16 pb-5 space-y-6 mt-auto">
        {messages.map((m, index) => {
          // Hide the most recent bot message while a thought is showing
          if (
            currentThought &&
            index === messages.length - 1 &&
            m.sender === "bot"
          ) {
            return null;
          }

          return (
            <div
              key={m.id}
              ref={index === targetIndex ? lastMessageRef : null}
              className="w-full scroll-mt-6"
            >
              {m.sender === "user" ? (
                <div className="flex justify-end">
                  <div className="chatgpt-user-bubble px-4 py-3 rounded-lg rounded-br-none max-w-[70%]">
                    <div className="text-sm leading-relaxed whitespace-pre-wrap">{m.text}</div>
                  </div>
                </div>
              ) : (
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
          );
        })}

        {showThinkingIndicator && (
          <div className="flex justify-start">
            <div className="px-4 py-3">
              <div className="flex items-center gap-2 h-5">
                <div className="w-2 h-2 bg-white rounded-full animate-pulse"></div>
                {currentThought && (
                  <span className="text-chatgpt-secondary italic text-sm leading-relaxed">
                    {currentThought}
                  </span>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Persistent spacer to keep older messages out of view */}
        <div className="h-[70vh] w-full flex-shrink-0 pointer-events-none" />

        {/* Always-present terminator element to allow reliable scrolling */}
        <div ref={bottomRef} />
      </div>
    </div>
  );
} 