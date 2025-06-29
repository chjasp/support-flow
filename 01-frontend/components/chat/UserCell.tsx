import React, { useRef, useEffect } from "react";
import { Play, Square, ChevronDown, Check, Trash2 } from "lucide-react";
import * as Select from "@radix-ui/react-select";

interface UserCellProps {
  // The text content of the cell. For editable cells, this is the controlled value.
  text: string;
  editable: boolean;
  interactionDisabled: boolean;
  onChange?: (val: string) => void; // Only for editable
  onRun: (val: string) => void;
  selectedModel?: string; // Only relevant for editable cell
  setSelectedModel?: React.Dispatch<React.SetStateAction<string>>;
  onDelete?: () => void;
  models?: string[];
  // Indicates that this cell is currently executing. When true, show a Stop button instead of Play.
  isRunning?: boolean;
  // Callback to stop the ongoing generation. Only relevant when isRunning === true.
  onStop?: () => void;
}

export const UserCell: React.FC<UserCellProps> = ({
  text,
  editable,
  interactionDisabled,
  onChange,
  onRun,
  selectedModel,
  setSelectedModel,
  onDelete,
  models = [],
  isRunning = false,
  onStop,
}) => {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Auto-resize textarea whenever text changes
  useEffect(() => {
    if (editable && textareaRef.current) {
      const el = textareaRef.current;
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 200) + "px";
    }
  }, [text, editable]);

  // Disable the Play button when interaction is disabled or no text is present.
  // When the cell is running, the Stop button should stay enabled.
  const runDisabled = (!isRunning && (interactionDisabled || !text.trim()));

  return (
    <div className="w-full border border-chatgpt-border rounded-md bg-chatgpt-input">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-1 border-b border-chatgpt-border">
        {isRunning ? (
          <button
            className="w-6 h-6 flex items-center justify-center text-white hover:text-chatgpt-secondary cursor-pointer transition-colors"
            onClick={onStop}
            title="Stop generation"
          >
            <Square className="w-4 h-4" strokeWidth={2} fill="currentColor" />
          </button>
        ) : (
          <button
            className={`w-6 h-6 flex items-center justify-center transition-colors ${
              runDisabled ? "text-[#4D4D5F] cursor-not-allowed" : "text-white hover:text-chatgpt-secondary cursor-pointer"
            }`}
            disabled={runDisabled}
            onClick={() => !runDisabled && onRun(text)}
            title="Run cell"
          >
            <Play className="w-4 h-4" strokeWidth={2} fill="currentColor" />
          </button>
        )}

        {/* Right side controls */}
        {editable ? (
          selectedModel && setSelectedModel && models.length > 0 && (
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
                    {models.map((model) => (
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
          )
        ) : (
          <button
            title="Delete cell"
            onClick={onDelete}
            className="w-5 h-5 flex items-center justify-center text-chatgpt hover:text-red-400 cursor-pointer"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Content */}
      <div className="p-4">
        {editable ? (
          <textarea
            ref={textareaRef}
            className="w-full min-h-[32px] max-h-[200px] bg-transparent border-0 text-sm text-chatgpt resize-none focus:outline-none leading-6 chatgpt-textarea placeholder:text-chatgpt-secondary"
            placeholder="Write a message …"
            value={text}
            onChange={(e) => {
              onChange?.(e.target.value);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (!runDisabled) {
                  onRun(text);
                }
              }
            }}
            disabled={interactionDisabled}
            rows={1}
          />
        ) : (
          <div className="text-sm leading-relaxed whitespace-pre-wrap">{text}</div>
        )}
      </div>
    </div>
  );
}; 