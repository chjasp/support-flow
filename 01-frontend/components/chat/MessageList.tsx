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
}

export function MessageList({ messages, isFetchingMessages, isLoading }: MessageListProps) {
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

  return (
    <div className="w-full">
      <div className="max-w-[720px] mx-auto px-4 py-5 space-y-6">
        {messages.map((m) => (
          <div
            key={m.id}
            className="w-full"
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
      </div>
    </div>
  );
} 