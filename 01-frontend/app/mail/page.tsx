"use client";

import { useState, useEffect } from "react";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import { Loader2, Send, Mail as MailIcon, Inbox } from "lucide-react";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { format } from 'date-fns';

// --- Define Backend URL (Use Environment Variables in production) ---
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8080"; // Adjust port if needed
const GENERATE_REPLY_ENDPOINT = `${API_BASE_URL}/api/generate-reply`; // <-- Define endpoint (adjust if different)
const REFINE_REPLY_ENDPOINT = `${API_BASE_URL}/api/refine-reply`; // <-- Define refinement endpoint (adjust if needed)
const LIST_MESSAGES_ENDPOINT = `${API_BASE_URL}/api/messages`;
const GET_MESSAGE_ENDPOINT = (msgId: string) => `${API_BASE_URL}/api/messages/${msgId}`;

// --- Types ---
interface ChatMessage {
  sender: "user" | "ai";
  text: string;
}

interface EmailMetadata {
  id: string;
  subject: string;
  from: string;
  date: string; // Keep as string (ms epoch) from backend for now
  snippet?: string;
}

interface EmailListResponse {
  messages: EmailMetadata[];
}

interface EmailBodyResponse {
  id: string;
  body: string;
}

// --- Helper: Fetcher function for SWR or basic fetch ---
const fetcher = (url: string) => fetch(url).then((res) => {
    if (!res.ok) {
        const error = new Error('An error occurred while fetching the data.');
        // Attach extra info to the error object.
        // error.info = await res.json(); // Can't do async here easily
        throw error;
    }
    return res.json();
});

export default function MailPage() {
  // --- State Variables ---
  const [receivedEmailContent, setReceivedEmailContent] = useState<string | null>(null);
  const [replyDraft, setReplyDraft] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);

  // --- Refinement Chat State ---
  const [refinementInput, setRefinementInput] = useState("");
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
  const [isRefining, setIsRefining] = useState(false);
  const [refinementError, setRefinementError] = useState<string | null>(null);

  // --- New State for Email List and Selection ---
  const [emailList, setEmailList] = useState<EmailMetadata[]>([]);
  const [selectedEmailId, setSelectedEmailId] = useState<string | null>(null);
  const [isFetchingList, setIsFetchingList] = useState(true);
  const [fetchListError, setFetchListError] = useState<string | null>(null);
  const [isFetchingBody, setIsFetchingBody] = useState(false);
  const [fetchBodyError, setFetchBodyError] = useState<string | null>(null);
  const [selectedEmailMetadata, setSelectedEmailMetadata] = useState<EmailMetadata | null>(null);

  // --- Fetch Email List ---
  useEffect(() => {
    const fetchEmailList = async () => {
      setIsFetchingList(true);
      setFetchListError(null);
      try {
        const data: EmailListResponse = await fetcher(LIST_MESSAGES_ENDPOINT);
        setEmailList(data.messages || []);
      } catch (err: any) {
        console.error("Error fetching email list:", err);
        setFetchListError(err.message || "Failed to load emails.");
      } finally {
        setIsFetchingList(false);
      }
    };
    fetchEmailList();
  }, []); // Fetch only once on mount

  // --- Fetch Selected Email Body ---
  useEffect(() => {
    if (!selectedEmailId) {
        setReceivedEmailContent(null); // Clear content if no email selected
        setSelectedEmailMetadata(null);
        return;
    }

    const fetchEmailBody = async () => {
      setIsFetchingBody(true);
      setFetchBodyError(null);
      setReceivedEmailContent(null); // Clear previous content while loading
      // Find metadata for the selected email
      const metadata = emailList.find(email => email.id === selectedEmailId);
      setSelectedEmailMetadata(metadata || null);

      try {
        const data: EmailBodyResponse = await fetcher(GET_MESSAGE_ENDPOINT(selectedEmailId));
        setReceivedEmailContent(data.body);
      } catch (err: any) {
        console.error(`Error fetching email body for ${selectedEmailId}:`, err);
        setFetchBodyError(err.message || `Failed to load email content.`);
        setReceivedEmailContent("Error loading email content."); // Show error in pane
      } finally {
        setIsFetchingBody(false);
      }
    };

    fetchEmailBody();
  }, [selectedEmailId, emailList]); // Re-run when selectedEmailId changes (or emailList, though less likely needed)

  // --- Handler Function: Generate Reply ---
  const handleGenerateReply = async () => {
    if (!receivedEmailContent) {
        setGenerateError("Please select an email first.");
        return;
    }
    setIsGenerating(true);
    setGenerateError(null);
    setReplyDraft("");

    try {
      const response = await fetch(GENERATE_REPLY_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email_content: receivedEmailContent }),
      });

      if (!response.ok) {
        let errorDetails = `Error: ${response.status} ${response.statusText}`;
        try {
          const errorData = await response.json();
          errorDetails = errorData.detail || errorDetails;
        } catch (e) { /* Ignore */ }
        throw new Error(`Failed to generate reply: ${errorDetails}`);
      }

      const data = await response.json();
      setReplyDraft(data.reply);

    } catch (err) {
      console.error("Error generating reply:", err);
      setGenerateError(err instanceof Error ? err.message : "An unknown error occurred.");
    } finally {
      setIsGenerating(false);
    }
  };

  // --- Handler Function: Refine Reply ---
  const handleRefineRequest = async () => {
    if (!refinementInput.trim() || !replyDraft.trim()) return;

    const userMessage: ChatMessage = { sender: "user", text: refinementInput };
    setChatHistory((prev) => [...prev, userMessage]);
    setRefinementInput("");
    setIsRefining(true);
    setRefinementError(null);

    try {
      // --- TODO: Implement actual API call for refinement ---
      console.log("Sending refinement instruction:", {
        draft: replyDraft,
        instruction: userMessage.text,
      });
      // Simulate API call delay
      await new Promise(resolve => setTimeout(resolve, 1500));

      // Placeholder response
      const aiResponse: ChatMessage = {
        sender: "ai",
        text: `Okay, here's a suggestion based on '${userMessage.text}': [Refined text would go here based on backend response]`,
      };
      // --- End of Placeholder ---

      /*
      // --- Actual API Call Example (uncomment when backend is ready) ---
      const response = await fetch(REFINE_REPLY_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          draft: replyDraft,
          instruction: userMessage.text,
        }),
      });

      if (!response.ok) {
        let errorDetails = `Error: ${response.status} ${response.statusText}`;
        try { const errorData = await response.json(); errorDetails = errorData.detail || errorDetails; } catch (e) { }
        throw new Error(`Failed to refine reply: ${errorDetails}`);
      }

      const data = await response.json();
      const aiResponse: ChatMessage = {
        sender: "ai",
        text: data.refined_reply, // Adjust based on actual API response structure
      };
      */

      setChatHistory((prev) => [...prev, aiResponse]);

    } catch (err) {
      console.error("Error refining reply:", err);
      const errorMsg = err instanceof Error ? err.message : "An unknown error occurred during refinement.";
      setRefinementError(errorMsg);
      setChatHistory((prev) => [...prev, { sender: "ai", text: `Error: ${errorMsg}` }]);
    } finally {
      setIsRefining(false);
    }
  };

  // --- Helper to format date ---
  const formatDate = (dateString: string | undefined) => {
      if (!dateString) return 'Unknown date';
      try {
          // Gmail internalDate is ms epoch, convert string to number
          return format(new Date(Number(dateString)), "yyyy-MM-dd HH:mm");
      } catch (e) {
          console.error("Error formatting date:", e);
          return 'Invalid date';
      }
  };

  return (
    <div className="flex flex-col flex-1">
      {/* Page Header Removed */}
      {/*
      <div className="px-6">
        <h1 className="text-3xl font-bold tracking-tight my-6">Mail</h1>
        <p className="text-muted-foreground mt-2 mb-4">
          Read emails and generate replies.
        </p>
      </div>
      */}

      {/* Main Resizable Layout */}
      <ResizablePanelGroup
        direction="horizontal"
        className="flex-1 border rounded-lg h-full p-4"
      >

        {/* Left Pane: Email List */}
        <ResizablePanel defaultSize={25} minSize={20} maxSize={40}>
          <div className="flex flex-col h-full">
            <div className="flex items-center justify-between p-2 mb-2 border-b">
                 <h2 className="text-lg font-semibold flex items-center">
                    <Inbox className="mr-2 h-5 w-5" /> Inbox
                 </h2>
                 {/* Optional: Add refresh button */}
            </div>
            <ScrollArea className="flex-1">
              {isFetchingList ? (
                // Skeleton Loader for List
                <div className="space-y-2">
                  <Skeleton className="h-16 w-full" />
                  <Skeleton className="h-16 w-full" />
                  <Skeleton className="h-16 w-full" />
                  <Skeleton className="h-16 w-full" />
                </div>
              ) : fetchListError ? (
                 <div className="p-4 text-center text-destructive">
                    <p>Error loading emails:</p>
                    <p className="text-sm">{fetchListError}</p>
                 </div>
              ) : emailList.length === 0 ? (
                 <div className="p-4 text-center text-muted-foreground">No emails found.</div>
              ) : (
                // Actual Email List
                emailList.map((email) => (
                  <div
                    key={email.id}
                    onClick={() => setSelectedEmailId(email.id)}
                    className={`p-3 border-b hover:bg-accent cursor-pointer rounded-md mb-1 ${
                      selectedEmailId === email.id ? "bg-accent border-primary" : "border-transparent"
                    }`}
                  >
                    <p className="text-sm font-medium truncate">{email.from || "Unknown Sender"}</p>
                    <p className="font-semibold truncate text-sm mt-0.5">{email.subject}</p>
                    <p className="text-xs text-muted-foreground truncate mt-0.5">{email.snippet}</p>
                    <p className="text-xs text-muted-foreground text-right mt-1">{formatDate(email.date)}</p>
                  </div>
                ))
              )}
            </ScrollArea>
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Middle Pane: Email Content & Reply Draft */}
        <ResizablePanel defaultSize={45} minSize={30}>
          <ResizablePanelGroup direction="vertical">
            {/* Top Section: Incoming Email */}
            <ResizablePanel defaultSize={50} minSize={30}>
              <div className="flex flex-col h-full p-4">
                <h2 className="text-xl font-semibold mb-2 flex items-center">
                    <MailIcon className="mr-2 h-5 w-5"/> Received Email
                </h2>
                {selectedEmailMetadata && (
                    <div className="text-sm text-muted-foreground mb-4 border-b pb-2">
                        <p><strong>From:</strong> {selectedEmailMetadata.from || 'N/A'}</p>
                        {/* Add To/Date if available and needed */}
                        <p><strong>Date:</strong> {formatDate(selectedEmailMetadata.date)}</p>
                        <p><strong>Subject:</strong> {selectedEmailMetadata.subject}</p>
                    </div>
                )}
                <ScrollArea className="flex-1">
                  {isFetchingBody ? (
                    <div className="space-y-2 p-2">
                        <Skeleton className="h-4 w-3/4" />
                        <Skeleton className="h-4 w-full" />
                        <Skeleton className="h-4 w-full" />
                        <Skeleton className="h-4 w-1/2" />
                    </div>
                  ) : fetchBodyError ? (
                     <p className="text-destructive">{fetchBodyError}</p>
                  ) : receivedEmailContent !== null ? (
                    <pre className="whitespace-pre-wrap text-sm">{receivedEmailContent}</pre>
                  ) : (
                    <p className="text-muted-foreground text-center mt-10">Select an email from the list to view its content.</p>
                  )}
                </ScrollArea>
                 {/* Generate Reply Button */}
                 <div className="mt-4 pt-4 border-t">
                   <Button
                     onClick={handleGenerateReply}
                     disabled={isGenerating || isFetchingBody || !selectedEmailId || !receivedEmailContent}
                   >
                     {isGenerating ? (
                       <> <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Generating... </>
                     ) : ( "Generate Response" )}
                   </Button>
                   {generateError && <p className="text-sm text-destructive mt-2">{generateError}</p>}
                 </div>
              </div>
            </ResizablePanel>

            <ResizableHandle withHandle />

            {/* Bottom Section: AI Reply Draft */}
            <ResizablePanel defaultSize={50} minSize={30}>
              <div className="flex flex-col h-full p-4">
                <h2 className="text-xl font-semibold mb-2">Draft</h2>
                <div className="flex-1 mb-4 border rounded p-2 bg-background">
                  <textarea
                    className="w-full h-full resize-none border-none outline-none bg-transparent text-sm"
                    placeholder={
                        !selectedEmailId ? "Select an email first." :
                        !receivedEmailContent ? "Load email content before generating." :
                        "Click 'Generate Response' above or edit manually..."
                    }
                    value={replyDraft}
                    onChange={(e) => setReplyDraft(e.target.value)}
                    readOnly={isGenerating || !selectedEmailId}
                  ></textarea>
                </div>
                {/* Action Toolbar Placeholder */}
                <div className="flex space-x-2 justify-end">
                  {/* Add Send/Discard buttons here if needed */}
                </div>
              </div>
            </ResizablePanel>
          </ResizablePanelGroup>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Right Pane: Refinement Chat Sidebar */}
        <ResizablePanel defaultSize={30} minSize={20} maxSize={40}>
           <div className="flex flex-col h-full p-4">
             <h2 className="text-xl font-semibold mb-4 border-b pb-2">Refine Reply</h2>
             <ScrollArea className="flex-1 mb-4 pr-4"> {/* Added pr-4 for scrollbar */}
               {chatHistory.length === 0 && !isRefining && (
                 <p className="text-sm text-muted-foreground text-center mt-4">
                   Generate a reply first, then ask for refinements here (e.g., "Make it shorter", "Sound more formal").
                 </p>
               )}
               {chatHistory.map((msg, index) => (
                 <div
                   key={index}
                   className={`mb-3 p-2 rounded-lg max-w-[85%] ${
                     msg.sender === "user"
                       ? "bg-primary text-primary-foreground ml-auto"
                       : "bg-muted mr-auto"
                   }`}
                 >
                   <p className="text-sm whitespace-pre-wrap">{msg.text}</p>
                 </div>
               ))}
               {isRefining && (
                 <div className="mb-3 p-2 rounded-lg max-w-[85%] bg-muted mr-auto flex items-center">
                    <Loader2 className="h-4 w-4 animate-spin mr-2"/>
                    <span className="text-sm">Thinking...</span>
                 </div>
               )}
               {refinementError && (
                 <div className="mb-3 p-2 rounded-lg max-w-[85%] bg-destructive/20 text-destructive-foreground mr-auto">
                    <p className="text-sm font-semibold">Error</p>
                    <p className="text-sm whitespace-pre-wrap">{refinementError}</p>
                 </div>
               )}
             </ScrollArea>
             <div className="mt-auto flex items-center gap-2 pt-4 border-t">
               <Input
                 placeholder="Type refinement instruction..."
                 value={refinementInput}
                 onChange={(e) => setRefinementInput(e.target.value)}
                 onKeyDown={(e) => e.key === 'Enter' && !isRefining && handleRefineRequest()}
                 disabled={isRefining || !replyDraft} // Disable if no draft or refining
                 className="flex-1"
               />
               <Button
                 onClick={handleRefineRequest}
                 disabled={isRefining || !refinementInput.trim() || !replyDraft}
                 size="icon"
               >
                 <Send className="h-4 w-4" />
               </Button>
             </div>
           </div>
        </ResizablePanel>

      </ResizablePanelGroup>
    </div>
  );
}
