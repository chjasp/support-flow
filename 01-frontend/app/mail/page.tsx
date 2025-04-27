"use client";

import { useState, useEffect } from "react";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import { Loader2, Send, Mail as MailIcon, Inbox, Trash2 } from "lucide-react";
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
const GET_INTERACTION_ENDPOINT = (emailId: string) => `${API_BASE_URL}/api/mail/interactions/${emailId}`;
const UPDATE_DRAFT_ENDPOINT = (emailId: string) => `${API_BASE_URL}/api/mail/interactions/${emailId}/draft`;
const ADD_REFINEMENT_ENDPOINT = (emailId: string) => `${API_BASE_URL}/api/mail/interactions/${emailId}/refinements`;
const CLEAR_REFINEMENT_ENDPOINT = (emailId: string) => `${API_BASE_URL}/api/mail/interactions/${emailId}/refinements`; // New endpoint (DELETE method)

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

interface EmailInteractionResponse {
    id: string;
    replyDraft: string | null; // Can be null from backend initially
    refinementHistory: ChatMessage[];
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
  const [isFetchingInteraction, setIsFetchingInteraction] = useState(false);
  const [fetchInteractionError, setFetchInteractionError] = useState<string | null>(null);
  const [isClearingHistory, setIsClearingHistory] = useState(false);
  const [clearHistoryError, setClearHistoryError] = useState<string | null>(null);

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

  // --- Fetch Selected Email Body AND Interaction Data ---
  useEffect(() => {
    if (!selectedEmailId) {
        setReceivedEmailContent(null);
        setSelectedEmailMetadata(null);
        setReplyDraft(""); // Clear draft when deselecting
        setChatHistory([]); // Clear history when deselecting
        setGenerateError(null);
        setRefinementError(null);
        setFetchInteractionError(null);
        return;
    }

    const fetchEmailData = async () => {
        // Reset states for the new email
        setIsFetchingBody(true);
        setIsFetchingInteraction(true);
        setFetchBodyError(null);
        setFetchInteractionError(null);
        setReceivedEmailContent(null);
        setReplyDraft(""); // Clear previous draft immediately
        setChatHistory([]); // Clear previous history immediately
        setGenerateError(null); // Clear errors from previous email
        setRefinementError(null);

        const metadata = emailList.find(email => email.id === selectedEmailId);
        setSelectedEmailMetadata(metadata || null);

        let bodyFetched = false;
        try {
            // Fetch body
            const bodyData: EmailBodyResponse = await fetcher(GET_MESSAGE_ENDPOINT(selectedEmailId));
            setReceivedEmailContent(bodyData.body);
            bodyFetched = true; // Mark body as fetched successfully
        } catch (err: any) {
            console.error(`Error fetching email body for ${selectedEmailId}:`, err);
            setFetchBodyError(err.message || `Failed to load email content.`);
            setReceivedEmailContent("Error loading email content.");
        } finally {
             setIsFetchingBody(false);
        }

        // --- Fetch interaction data (only if body fetch was attempted, even if failed) ---
        try {
            const interactionRes = await fetch(GET_INTERACTION_ENDPOINT(selectedEmailId));
            // No need to check 404, backend sends default structure
            if (!interactionRes.ok) {
                const errorData = await interactionRes.json().catch(() => ({})); // Try to parse error
                throw new Error(`Failed to fetch interaction data: ${interactionRes.statusText} ${errorData.detail || ''}`);
            }
            const interactionData: EmailInteractionResponse = await interactionRes.json();
            setReplyDraft(interactionData.replyDraft || ""); // Use fetched draft or default empty string
            setChatHistory(interactionData.refinementHistory || []); // Use fetched history or default empty array
            console.log(`Loaded interaction data for ${selectedEmailId}`);
        } catch (interactionErr: any) {
             console.error(`Error fetching interaction data for ${selectedEmailId}:`, interactionErr);
             setFetchInteractionError(interactionErr.message || "Failed to load saved draft/history.");
             // Keep default empty state for draft/history on error
             setReplyDraft("");
             setChatHistory([]);
        } finally {
             setIsFetchingInteraction(false);
        }
    };

    fetchEmailData();
  }, [selectedEmailId, emailList]); // Dependencies

  // --- Handler Function: Generate Reply ---
  const handleGenerateReply = async () => {
    // Ensure selectedEmailId is checked
    if (!receivedEmailContent || !selectedEmailId) {
        setGenerateError("Please select and load an email first.");
        return;
    }
    setIsGenerating(true);
    setGenerateError(null);
    // setReplyDraft(""); // Clear local draft visually immediately

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
      const newDraft = data.reply;
      setReplyDraft(newDraft); // Update local state

      // --- Save the generated draft to Firestore (fire-and-forget or handle error) ---
      fetch(UPDATE_DRAFT_ENDPOINT(selectedEmailId), {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ draft: newDraft }),
      })
      .then(saveResponse => {
          if (!saveResponse.ok) {
              console.error(`Failed to save generated draft for ${selectedEmailId}: ${saveResponse.statusText}`);
              // Optionally: setSaveDraftError("Could not save draft.");
          } else {
               console.log(`Saved generated draft for ${selectedEmailId}`);
               // Optionally: setSaveDraftError(null);
          }
      })
      .catch(saveErr => {
          console.error(`Error saving generated draft for ${selectedEmailId}:`, saveErr);
          // Optionally: setSaveDraftError("Could not save draft.");
      });
      // ------------------------------------------

    } catch (err) {
      console.error("Error generating reply:", err);
      const errorMsg = err instanceof Error ? err.message : "An unknown error occurred.";
      setGenerateError(errorMsg);
      setReplyDraft(""); // Clear draft on generation error
    } finally {
      setIsGenerating(false);
    }
  };

  // --- Handler Function: Refine Reply ---
  const handleRefineRequest = async () => {
    // Add selectedEmailId check
    if (!refinementInput.trim() || !replyDraft.trim() || !receivedEmailContent || !selectedEmailId) {
        setRefinementError("Cannot refine without original email, a draft, an instruction, and a selected email.");
        return;
    }

    const userMessage: ChatMessage = { sender: "user", text: refinementInput };
    const currentInstruction = refinementInput;

    // --- Prepare for API calls ---
    setRefinementInput(""); // Clear input immediately
    setIsRefining(true);
    setRefinementError(null);
    // setSaveHistoryError(null); // Reset save error state if using one
    // setSaveDraftError(null);

    let userMessageSaved = false;
    try {
        // --- 1. Save User Message to Firestore FIRST ---
        const saveUserMsgResponse = await fetch(ADD_REFINEMENT_ENDPOINT(selectedEmailId), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(userMessage),
        });
        if (!saveUserMsgResponse.ok) {
            throw new Error(`Failed to save your message: ${saveUserMsgResponse.statusText}`);
        }
        userMessageSaved = true;
        // --- Update local chat history ONLY AFTER successful save ---
        setChatHistory((prev) => [...prev, userMessage]);
        console.log(`Saved user refinement message for ${selectedEmailId}`);


        // --- 2. Call Backend for Refinement ---
        const response = await fetch(REFINE_REPLY_ENDPOINT, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              email_content: receivedEmailContent,
              current_draft: replyDraft,
              instruction: currentInstruction,
            }),
        });
        if (!response.ok) {
            let errorDetails = `Error: ${response.status} ${response.statusText}`;
            try { const errorData = await response.json(); errorDetails = errorData.detail || errorDetails; } catch (e) {}
            throw new Error(`Failed to refine reply: ${errorDetails}`);
        }
        const data: { refined_reply: string } = await response.json();
        const refinedDraft = data.refined_reply;
        const aiResponse: ChatMessage = { sender: "ai", text: refinedDraft };


        // --- 3. Save AI Response to Firestore ---
        // We attempt this even if saving the draft below fails
        fetch(ADD_REFINEMENT_ENDPOINT(selectedEmailId), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(aiResponse),
        })
        .then(saveAiMsgResponse => {
            if (!saveAiMsgResponse.ok) {
                console.error(`Failed to save AI refinement message for ${selectedEmailId}: ${saveAiMsgResponse.statusText}`);
                // setSaveHistoryError("Failed to save AI response.");
                // Still update local history, maybe with an indicator?
                setChatHistory((prev) => [...prev, { ...aiResponse, text: `(Save Error) ${aiResponse.text}` }]);
            } else {
                // --- Update local chat history ONLY AFTER successful save ---
                setChatHistory((prev) => [...prev, aiResponse]);
                console.log(`Saved AI refinement message for ${selectedEmailId}`);
            }
        })
        .catch(saveErr => {
             console.error(`Error saving AI refinement message for ${selectedEmailId}:`, saveErr);
             // setSaveHistoryError("Failed to save AI response.");
             setChatHistory((prev) => [...prev, { ...aiResponse, text: `(Save Error) ${aiResponse.text}` }]);
        });


    } catch (err) {
        console.error("Error during refinement process:", err);
        const errorMsg = err instanceof Error ? err.message : "An unknown error occurred during refinement.";
        setRefinementError(errorMsg);
        // Add error message to local chat history if user message was saved
        if (userMessageSaved) {
             setChatHistory((prev) => [...prev, { sender: "ai", text: `Error: ${errorMsg}` }]);
        }
    } finally {
        setIsRefining(false);
    }
  };

  // --- Handler Function: Clear Refinement History ---
  const handleClearRefinementHistory = async () => {
    if (!selectedEmailId || chatHistory.length === 0) {
        // Should not happen if button is disabled correctly, but good practice
        return;
    }

    // Optional: Confirmation dialog
    // if (!window.confirm("Are you sure you want to clear the refinement history? This cannot be undone.")) {
    //     return;
    // }

    setIsClearingHistory(true);
    setClearHistoryError(null);
    setRefinementError(null); // Clear previous refinement errors

    try {
        const response = await fetch(CLEAR_REFINEMENT_ENDPOINT(selectedEmailId), {
            method: "DELETE",
        });

        if (!response.ok) {
            let errorDetails = `Error: ${response.status} ${response.statusText}`;
            try {
                const errorData = await response.json();
                errorDetails = errorData.detail || errorDetails;
            } catch (e) { /* Ignore if response not JSON */ }
            throw new Error(`Failed to clear history: ${errorDetails}`);
        }

        // --- Clear local state on success ---
        setChatHistory([]);
        console.log(`Cleared refinement history for ${selectedEmailId}`);

    } catch (err) {
        console.error("Error clearing refinement history:", err);
        const errorMsg = err instanceof Error ? err.message : "An unknown error occurred.";
        setClearHistoryError(errorMsg); // Display error specific to clearing
        // Optionally display this error in the chat area as well or instead
        // setRefinementError(`Failed to clear history: ${errorMsg}`);
    } finally {
        setIsClearingHistory(false);
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
    <div className="flex flex-col p-4 h-[calc(100vh-theme(space.14)-theme(space.6))]">

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
                     disabled={isGenerating || isFetchingBody || isFetchingInteraction || !selectedEmailId || !receivedEmailContent}
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
                <h2 className="text-xl font-semibold mb-2">Reply</h2>
                {/* Show interaction loading/error? */}
                 {fetchInteractionError && <p className="text-sm text-destructive mb-2">Error loading saved draft: {fetchInteractionError}</p>}
                <div className="flex-1 mb-4 border rounded p-2 bg-background">
                    <textarea
                        className="w-full h-full resize-none border-none outline-none bg-transparent text-sm"
                        placeholder={
                            isFetchingInteraction ? "Loading saved draft..." :
                            !selectedEmailId ? "Select an email first." :
                            isFetchingBody ? "Loading email content..." : // Check body loading too
                            !receivedEmailContent ? "Load email content before generating." :
                            "Click 'Generate Response' above or edit manually..."
                        }
                        value={replyDraft}
                        onChange={(e) => {
                            setReplyDraft(e.target.value);
                            // TODO: Implement debounced save for manual edits here if desired
                        }}
                        // Disable if generating, fetching body/interaction, or no email selected
                        readOnly={isGenerating || isFetchingBody || isFetchingInteraction || !selectedEmailId}
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
           {/* Main container: Flex column, full height */}
           <div className="flex flex-col h-full">
             {/* Header: Fixed height, padding, prevent shrinking, add button */}
             <div className="flex items-center justify-between border-b pb-2 px-4 pt-4 flex-shrink-0">
                 <h2 className="text-xl font-semibold">Refine Reply</h2>
                 <Button
                    variant="ghost" // Use ghost or outline for less emphasis
                    size="icon"
                    onClick={handleClearRefinementHistory}
                    disabled={!selectedEmailId || chatHistory.length === 0 || isRefining || isFetchingInteraction || isClearingHistory}
                    title="Clear refinement history" // Tooltip
                 >
                    {isClearingHistory ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                        <Trash2 className="h-4 w-4" />
                    )}
                 </Button>
             </div>

             {/* Scrollable Chat Area: Takes remaining space, allows vertical scroll */}
             <div className="flex-1 min-h-0 overflow-y-auto px-4">
               {/* Added pb-4 for spacing at the bottom of the scrollable content */}
               <div className="space-y-3 pb-4">
                 {/* Show interaction loading/error? */}
                 {isFetchingInteraction && chatHistory.length === 0 && (
                     <p className="text-sm text-muted-foreground text-center mt-4">Loading history...</p>
                 )}
                 {fetchInteractionError && chatHistory.length === 0 && (
                     <p className="text-sm text-destructive text-center mt-4">Error loading history: {fetchInteractionError}</p>
                 )}
                 {chatHistory.length === 0 && !isRefining && !isFetchingInteraction && !fetchInteractionError && (
                     <p className="text-sm text-muted-foreground text-center mt-4">
                         Generate a reply first, then ask for refinements here (e.g., "Make it shorter", "Sound more formal").
                     </p>
                 )}

                 {/* Display Clear History Error */}
                 {clearHistoryError && (
                    <div className="p-2 rounded-lg bg-destructive/20 text-destructive-foreground text-center">
                        <p className="text-sm font-semibold">Error clearing history:</p>
                        <p className="text-sm">{clearHistoryError}</p>
                    </div>
                 )}

                 {chatHistory.map((msg, index) => (
                   <div
                     key={index}
                     className={`p-2 rounded-lg max-w-[85%] ${
                       msg.sender === "user"
                         ? "bg-primary text-primary-foreground ml-auto"
                         : "bg-muted mr-auto"
                     }`}
                   >
                     <p className="text-sm whitespace-pre-wrap">{msg.text}</p>
                   </div>
                 ))}

                 {isRefining && (
                   <div className="p-2 rounded-lg max-w-[85%] bg-muted mr-auto flex items-center">
                     <Loader2 className="h-4 w-4 animate-spin mr-2" />
                     <span className="text-sm">Thinking...</span>
                   </div>
                 )}

                 {refinementError && (
                   <div className="p-2 rounded-lg max-w-[85%] bg-destructive/20 text-destructive-foreground mr-auto">
                     <p className="text-sm font-semibold">Error</p>
                     <p className="text-sm whitespace-pre-wrap">{refinementError}</p>
                   </div>
                 )}
               </div>
             </div>

             {/* Input Area: Fixed height, pushed to bottom, prevent shrinking */}
             <div className="flex items-center gap-2 pt-4 border-t px-4 pb-4 flex-shrink-0">
               <Input
                 placeholder="Type refinement instruction..."
                 value={refinementInput}
                 onChange={(e) => setRefinementInput(e.target.value)}
                 onKeyDown={(e) => e.key === 'Enter' && !isRefining && !isFetchingInteraction && handleRefineRequest()} // Check isFetchingInteraction
                 // Disable if refining, no draft, or fetching interaction data
                 disabled={isRefining || !replyDraft || isFetchingInteraction}
                 className="flex-1"
               />
               <Button
                 onClick={handleRefineRequest}
                 // Disable if refining, no input, no draft, or fetching interaction data
                 disabled={isRefining || !refinementInput.trim() || !replyDraft || isFetchingInteraction}
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