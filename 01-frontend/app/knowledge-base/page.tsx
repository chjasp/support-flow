"use client"; // Add this directive for using state and effects

import React, { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button"; // Assuming you use shadcn/ui
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Trash2,
  FileText,
  FileUp,
  ClipboardPaste,
  Loader2,
} from "lucide-react"; // Example icons

// Define a type for knowledge items (replace with your actual data structure)
type KnowledgeItem = {
  id: string;
  name: string;
  type: "Document" | "Pasted Text";
  fileType?: string; // e.g., 'PDF', 'DOCX'
  dateAdded: string; // Use string for simplicity, Date object is better
  status: "Uploading" | "Processing" | "Ready" | "Error" | "Unknown";
  gcsUri?: string; // Store GCS URI if applicable
  uploadError?: string; // Store upload error message
};

// Placeholder data - replace with actual data fetching
const placeholderItems: KnowledgeItem[] = [
  {
    id: "1",
    name: "faq.pdf",
    type: "Document",
    fileType: "PDF",
    dateAdded: "2023-10-27",
    status: "Ready",
  },
  {
    id: "2",
    name: "Website - Return Policy",
    type: "Pasted Text",
    dateAdded: "2023-10-26",
    status: "Processing",
  },
  {
    id: "3",
    name: "onboarding.docx",
    type: "Document",
    fileType: "DOCX",
    dateAdded: "2023-10-25",
    status: "Error",
  },
  {
    id: "4",
    name: "support_scripts.txt",
    type: "Document",
    fileType: "TXT",
    dateAdded: "2023-10-24",
    status: "Ready",
  },
];

// --- Define Backend URLs (Use Environment Variables in production) ---
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:5147"; // Your FastAPI backend URL
const GENERATE_UPLOAD_URL_ENDPOINT = "/api/generate-upload-url"; // Next.js API route
const GET_ITEMS_ENDPOINT = `${API_BASE_URL}/documents`; // Add the new endpoint URL
const DELETE_ITEM_ENDPOINT = `${API_BASE_URL}/documents`; // Define the base URL for delete

export default function KnowledgeBasePage() {
  const [activeView, setActiveView] = useState<"overview" | "upload">(
    "overview"
  );
  const [knowledgeItems, setKnowledgeItems] = useState<KnowledgeItem[]>([]); // Start empty
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [pastedTitle, setPastedTitle] = useState("");
  const [pastedContent, setPastedContent] = useState("");
  const [isLoading, setIsLoading] = useState(false); // Loading state for uploads/saves
  const [isFetchingItems, setIsFetchingItems] = useState(true); // Keep initial loading state

  // --- Fetch Data Logic (extracted) ---
  const fetchItems = useCallback(async (isInitialLoad = false) => {
    // Only set global fetching state on initial load
    if (isInitialLoad) {
      setIsFetchingItems(true);
      setKnowledgeItems([]); // Clear on initial load
    }
    console.log(`Fetching knowledge items from: ${GET_ITEMS_ENDPOINT}`);
    try {
      const response = await fetch(GET_ITEMS_ENDPOINT);
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(
          `Failed to fetch items: ${response.status} ${response.statusText} - ${errorText}`
        );
      }
      const data: KnowledgeItem[] = await response.json();
      console.log("Fetched items:", data);

      // Update state: Replace the whole list or merge based on IDs
      // For simplicity with polling, replacing is easier if backend returns full list
      setKnowledgeItems(data);

    } catch (error) {
      console.error("Error fetching knowledge items:", error);
      // TODO: Show error to user (e.g., using a toast notification)
      if (isInitialLoad) {
        setKnowledgeItems([]); // Set to empty on initial load error
      } // Don't clear items if a poll fails, keep the last known state
    } finally {
      if (isInitialLoad) {
        setIsFetchingItems(false);
      }
    }
  }, []); // Empty dependency array as it doesn't depend on component state/props directly

  // --- Initial Data Fetch ---
  useEffect(() => {
    fetchItems(true); // Pass true for initial load
  }, [fetchItems]); // Depend on the memoized fetchItems function

  // --- Polling Logic ---
  useEffect(() => {
    // Check if there are items currently being processed or uploaded
    const itemsToPoll = knowledgeItems.filter(
      (item) => item.status === "Processing" || item.status === "Uploading"
    );

    let intervalId: NodeJS.Timeout | null = null;

    if (itemsToPoll.length > 0) {
      console.log(`Polling status for ${itemsToPoll.length} item(s)...`);
      intervalId = setInterval(() => {
        console.log("Polling interval triggered...");
        fetchItems(false); // Fetch updates, not initial load
      }, 10000); // Poll every 10 seconds
    } else {
      console.log("No items in Processing/Uploading state. Stopping polling.");
    }

    // Cleanup function: clear interval when component unmounts or dependencies change
    return () => {
      if (intervalId) {
        console.log("Clearing polling interval.");
        clearInterval(intervalId);
      }
    };
  }, [knowledgeItems, fetchItems]); // Re-run effect if items or fetchItems change

  // --- Event Handlers ---

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) {
      setSelectedFiles(Array.from(event.target.files));
    }
  };

  const handleUploadFiles = async () => {
    if (selectedFiles.length === 0) return;

    setIsLoading(true);
    const uploadPromises = selectedFiles.map(async (file) => {
      const tempId = crypto.randomUUID();
      const fileType = file.name.split(".").pop()?.toUpperCase();

      const newItem: KnowledgeItem = {
        id: tempId,
        name: file.name,
        type: "Document",
        fileType: fileType,
        dateAdded: new Date().toISOString().split("T")[0],
        status: "Uploading",
      };
      setKnowledgeItems((prev) => [newItem, ...prev]);

      try {
        // 1. Get Signed URL and Metadata Headers from our Next.js API route
        console.log(`Requesting signed URL for: ${file.name}`);
        const signedUrlResponse = await fetch(GENERATE_UPLOAD_URL_ENDPOINT, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filename: file.name, contentType: file.type }),
        });

        if (!signedUrlResponse.ok) {
          const errorData = await signedUrlResponse.json();
          throw new Error(
            `Failed to get signed URL: ${
              errorData.error || signedUrlResponse.statusText
            }`
          );
        }

        // Destructure the metadataHeaders along with other data
        const { signedUrl, gcsUri, objectName, metadataHeaders } =
          await signedUrlResponse.json();
        console.log(`Got signed URL for ${objectName}, starting upload...`);

        // Update item status to 'Uploading' (or keep it) before GCS PUT
        setKnowledgeItems((prev) =>
          prev.map(
            (item) =>
              item.id === tempId
                ? { ...item, status: "Uploading", gcsUri: gcsUri }
                : item // Store GCS URI early
          )
        );

        // 2. Upload file directly to GCS using the Signed URL, including metadata headers
        const uploadHeaders = new Headers({
          "Content-Type": file.type,
        });
        // Add all metadata headers returned by the API route
        if (metadataHeaders) {
          for (const [key, value] of Object.entries(metadataHeaders)) {
            uploadHeaders.append(key, value as string);
          }
        }

        const uploadResponse = await fetch(signedUrl, {
          method: "PUT",
          headers: uploadHeaders, // Use headers with metadata
          body: file,
        });

        if (!uploadResponse.ok) {
          throw new Error(`GCS Upload failed: ${uploadResponse.statusText}`);
        }
        console.log(`Successfully uploaded ${file.name} to ${gcsUri}`);

        // Update item status to 'Processing' - indicating the upload is done and backend processing *should* start soon.
        // The final 'Ready' or 'Error' status needs to be updated via another mechanism (polling, websocket, etc.)
        setKnowledgeItems((prev) =>
          prev.map((item) =>
            item.id === tempId
              ? { ...item, status: "Processing", gcsUri: gcsUri }
              : item
          )
        );

        // We don't get the doc_id back immediately anymore.
        // The tempId will remain until the list is refreshed or updated via polling/websockets.

        return { success: true, name: file.name };
      } catch (error) {
        console.error(`Error uploading ${file.name}:`, error);
        const errorMessage =
          error instanceof Error ? error.message : "Unknown upload error";
        setKnowledgeItems((prev) =>
          prev.map((item) =>
            item.id === tempId
              ? { ...item, status: "Error", uploadError: errorMessage }
              : item
          )
        );
        return { success: false, name: file.name, error: errorMessage };
      }
    });

    const results = await Promise.all(uploadPromises);
    const failedUploads = results.filter((r) => !r.success);

    if (failedUploads.length > 0) {
      alert(
        `Failed to upload ${failedUploads.length} file(s). Check console and item status.`
      );
    } else {
      // Adjust success message as processing is now asynchronous
      alert(
        `Successfully uploaded ${selectedFiles.length} file(s). Processing will start automatically. Status will update later.`
      );
    }

    setSelectedFiles([]);
    setIsLoading(false);

    // Optional: Trigger a re-fetch of the list after uploads finish to get updated statuses sooner
    // await fetchItems(); // You might need to extract fetchItems to be callable here
  };

  const handleSavePastedText = async () => {
    if (!pastedTitle || !pastedContent) {
      alert("Please provide both a title and content.");
      return;
    }
    setIsLoading(true);
    const tempId = crypto.randomUUID(); // Generate temporary ID for optimistic UI

    // Sanitize title slightly for filename, replace spaces, keep it simple
    const safeTitleBase = pastedTitle.replace(/[^a-zA-Z0-9_-]/g, '_').replace(/\s+/g, '-');
    // Ensure it's not too long and add .txt extension
    const filename = `${safeTitleBase.substring(0, 50) || 'pasted-text'}.txt`;
    const contentType = "text/plain"; // Content type for plain text

    // Optimistic UI update (similar to file upload)
    const newItem: KnowledgeItem = {
      id: tempId,
      name: pastedTitle, // Display the original title
      type: "Pasted Text", // Keep this type for UI distinction
      fileType: "TXT", // Indicate it's treated as TXT
      dateAdded: new Date().toISOString().split("T")[0],
      status: "Uploading", // Start with 'Uploading'
    };
    setKnowledgeItems((prev) => [newItem, ...prev]);
    const originalTitle = pastedTitle; // Store original values before clearing
    const originalContent = pastedContent;
    setPastedTitle(""); // Clear form immediately
    setPastedContent("");

    try {
      // 1. Get Signed URL for the text file
      console.log(`Requesting signed URL for text: ${filename}`);
      const signedUrlResponse = await fetch(GENERATE_UPLOAD_URL_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // Send filename, content type, AND the original title for metadata signing
        body: JSON.stringify({
            filename: filename, // The unique name for the GCS object
            contentType: contentType,
            originalTitle: originalTitle // Send the original title
        }),
      });

      if (!signedUrlResponse.ok) {
        const errorData = await signedUrlResponse.json();
        throw new Error(
          `Failed to get signed URL for text: ${
            errorData.error || signedUrlResponse.statusText
          }`
        );
      }

      // Destructure metadataHeaders correctly
      const { signedUrl, gcsUri, objectName, metadataHeaders } =
        await signedUrlResponse.json();
      console.log(`Got signed URL for ${objectName}, starting text upload...`);

      // Update item status to 'Uploading' and store GCS URI
      setKnowledgeItems((prev) =>
        prev.map((item) =>
          item.id === tempId
            ? { ...item, status: "Uploading", gcsUri: gcsUri } // Store GCS URI
            : item
        )
      );

      // 2. Create a Blob from the pasted content
      const textBlob = new Blob([originalContent], { type: contentType });

      // 3. Upload the Blob to GCS using the Signed URL
      const uploadHeaders = new Headers({
        "Content-Type": contentType, // Set content type for the upload
      });

      // Add the required metadata header(s) EXACTLY as returned by the API
      if (metadataHeaders) {
        for (const [key, value] of Object.entries(metadataHeaders)) {
           // Append the exact header name and value returned by the API route
           uploadHeaders.append(key, value as string);
        }
      } else {
          console.warn("Metadata headers not received from signed URL endpoint. Metadata might be missing on GCS object.");
          // Attempt upload without the header if not provided (might fail if backend requires it)
      }

      console.log("Uploading text blob to GCS with headers:", Object.fromEntries(uploadHeaders.entries()));

      const uploadResponse = await fetch(signedUrl, {
        method: "PUT",
        headers: uploadHeaders, // Use headers with metadata
        body: textBlob, // Upload the Blob
      });

      if (!uploadResponse.ok) {
        // Attempt to get error details from GCS response
        let gcsErrorDetails = `GCS Upload failed: ${uploadResponse.status} ${uploadResponse.statusText}`;
        try {
            const errorText = await uploadResponse.text();
            gcsErrorDetails += ` - ${errorText}`;
        } catch (_) { /* Ignore if can't read text */ }
        throw new Error(gcsErrorDetails);
      }
      console.log(`Successfully uploaded text content as ${filename} to ${gcsUri}`);

      // Update item status to 'Processing' - backend will take over via GCS trigger
      setKnowledgeItems((prev) =>
        prev.map((item) =>
          item.id === tempId
            ? { ...item, status: "Processing" } // GCS URI already stored
            : item
        )
      );

      // Optional: Show success notification
      alert(`"${originalTitle}" uploaded successfully. Processing will start automatically. Status will update later.`);

    } catch (error) {
      console.error("Error saving pasted text:", error);
      const errorMessage =
        error instanceof Error ? error.message : "Unknown error saving text";

      // Update the optimistic item to show error status
      setKnowledgeItems((prev) =>
        prev.map((item) =>
          item.id === tempId
            ? { ...item, status: "Error", uploadError: errorMessage }
            : item
        )
      );

      // Restore form fields if needed, or show error message
      setPastedTitle(originalTitle); // Optional: Restore content on error
      setPastedContent(originalContent);
      alert(`Error saving text: ${errorMessage}`);
      // TODO: Implement better error display (e.g., toast notification)

    } finally {
      setIsLoading(false); // Reset loading state regardless of success/error
    }
  };

  const handleDeleteItem = async (id: string, name: string) => {
    // 1. Confirmation Dialog
    if (!window.confirm(`Are you sure you want to delete "${name}"? This action cannot be undone.`)) {
      return; // Stop if user cancels
    }

    console.log("Attempting to delete item:", id);
    // Store the item to potentially restore on error (optional but good practice)
    const itemToDelete = knowledgeItems.find(item => item.id === id);
    if (!itemToDelete) {
        console.warn("Item to delete not found in current state:", id);
        return; // Should not happen if button is clicked on an existing item
    }

    // 2. Optimistic UI update: Remove the item immediately
    setKnowledgeItems((prev) => prev.filter((item) => item.id !== id));

    try {
      // 3. Call the Backend API
      const response = await fetch(`${DELETE_ITEM_ENDPOINT}/${id}`, { // Append ID to URL
        method: "DELETE",
        headers: {
            // Add any necessary headers like Authorization if needed in the future
            // 'Authorization': `Bearer ${your_token}`
        }
      });

      // 4. Handle Response
      if (!response.ok) {
        // If the response status code is not 2xx (e.g., 404, 500)
        let errorDetails = `Status: ${response.status} ${response.statusText}`;
        try {
            // Try to parse potential JSON error from backend
            const errorData = await response.json();
            errorDetails += ` - ${errorData.detail || JSON.stringify(errorData)}`;
        } catch (parseError) {
            // If response is not JSON, try to read as text
            try {
                const errorText = await response.text();
                errorDetails += ` - ${errorText || 'No further details'}`;
            } catch (textError) {
                 // Ignore if text cannot be read
            }
        }
        throw new Error(`Failed to delete item: ${errorDetails}`);
      }

      // Success! (Status code 204 No Content doesn't have a body)
      console.log(`Successfully deleted item ID: ${id} from backend.`);
      // Optional: Show success notification (e.g., using a toast library)
      // showToast(`"${name}" deleted successfully.`);

    } catch (error) {
      console.error("Error deleting item:", error);

      // 5. Rollback UI update on error
      // Add the item back to the list. This simple version adds it back to the start.
      // A more robust solution might try to re-insert at the original position or sort again.
      setKnowledgeItems((prev) => [itemToDelete, ...prev].sort((a, b) => new Date(b.dateAdded).getTime() - new Date(a.dateAdded).getTime())); // Example sort

      // Show error message to user
      const errorMessage = error instanceof Error ? error.message : String(error);
      alert(`Failed to delete "${name}".\nError: ${errorMessage}`);
      // TODO: Replace alert with a better notification system (e.g., toast)
    }
    // Optional: Add a finally block if you need to reset a specific 'deleting' state
  };

  return (
    <div className="flex h-[calc(100vh-theme(space.14))] bg-background">
      {" "}
      {/* Adjust height based on header */}
      {/* Sidebar */}
      <aside className="w-64 border-r p-4 flex flex-col space-y-2 overflow-y-auto">
        <h2 className="text-xl font-semibold mb-4">Knowledge Base</h2>
        <Button
          variant={activeView === "overview" ? "secondary" : "ghost"}
          className="justify-start"
          onClick={() => setActiveView("overview")}
        >
          <FileText className="mr-2 h-4 w-4" /> Overview
        </Button>
        <Button
          variant={activeView === "upload" ? "secondary" : "ghost"}
          className="justify-start"
          onClick={() => setActiveView("upload")}
        >
          <FileUp className="mr-2 h-4 w-4" /> Upload
        </Button>
        {/* Optional: Add Summary Stats here */}
        {/*
         <div className="mt-auto pt-4 border-t">
            <h3 className="text-sm font-medium text-muted-foreground mb-2">Stats</h3>
            <p className="text-xs">Total Items: {knowledgeItems.length}</p>
            <p className="text-xs">Ready: {knowledgeItems.filter(i => i.status === 'Ready').length}</p>
         </div>
         */}
      </aside>
      {/* Main Content Area */}
      <main className="flex-1 p-6 overflow-auto">
        {activeView === "overview" && (
          <div>
            <h1 className="text-3xl font-bold tracking-tight mb-2">
              Knowledge Base Overview
            </h1>
            <p className="text-muted-foreground mb-6">
              View and manage your knowledge base articles and documents.
            </p>

            {/* Optional Search Bar */}
            <div className="mb-4">
              <Input
                type="search"
                placeholder="Search by name or title..."
                className="max-w-sm"
              />
            </div>

            {/* Knowledge Items List/Table */}
            <Card>
              <CardContent className="p-0">
                {" "}
                {/* Remove padding for full-width table */}
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Name</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Date Added</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {isFetchingItems ? (
                      <TableRow>
                        <TableCell colSpan={5} className="text-center h-24">
                          <Loader2 className="h-6 w-6 animate-spin inline-block mr-2" />{" "}
                          Loading items...
                        </TableCell>
                      </TableRow>
                    ) : knowledgeItems.length > 0 ? (
                      knowledgeItems.map((item) => (
                        <TableRow key={item.id}>
                          <TableCell className="font-medium">
                            {item.name}
                          </TableCell>
                          <TableCell>
                            {item.type === "Document"
                              ? `Doc (${item.fileType || "?"})`
                              : "Text"}
                          </TableCell>
                          <TableCell>{item.dateAdded}</TableCell>
                          <TableCell>
                            <span
                              className={`px-2 py-1 rounded-full text-xs font-medium flex items-center w-fit ${
                                // Added flex/items-center/w-fit
                                item.status === "Ready"
                                  ? "bg-green-100 text-green-800"
                                  : item.status === "Processing"
                                  ? "bg-yellow-100 text-yellow-800"
                                  : item.status === "Uploading"
                                  ? "bg-blue-100 text-blue-800" // Added Uploading style
                                  : item.status === "Error"
                                  ? "bg-red-100 text-red-800"
                                  : "bg-gray-100 text-gray-800"
                              }`}
                            >
                              {(item.status === "Uploading" ||
                                item.status === "Processing") && (
                                <Loader2 className="h-3 w-3 animate-spin mr-1" />
                              )}{" "}
                              {/* Spinner */}
                              {item.status}
                            </span>
                            {item.status === "Error" && item.uploadError && (
                              <p
                                className="text-xs text-red-600 mt-1"
                                title={item.uploadError}
                              >
                                Error: {item.uploadError.substring(0, 50)}
                                {item.uploadError.length > 50 ? "..." : ""}
                              </p>
                            )}
                          </TableCell>
                          <TableCell className="text-right">
                            <Button
                              variant="ghost"
                              size="icon"
                              // Pass both id and name to the handler
                              onClick={() => handleDeleteItem(item.id, item.name)}
                              disabled={
                                item.status === "Uploading" ||
                                item.status === "Processing"
                              } // Keep disabling during processing
                              title={`Delete ${item.name}`} // Add title for accessibility/tooltip
                              className="cursor-pointer"
                            >
                              <Trash2 className="h-4 w-4" />
                              <span className="sr-only">Delete</span>
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))
                    ) : (
                      <TableRow>
                        <TableCell
                          colSpan={5}
                          className="text-center text-muted-foreground h-24"
                        >
                          No knowledge items found. Add some!
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>
        )}

        {activeView === "upload" && (
          <div>
            <h1 className="text-3xl font-bold tracking-tight mb-6">
              Add to Knowledge Base
            </h1>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Section 1: Upload Files */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center">
                    <FileUp className="mr-2 h-5 w-5" /> Upload Documents
                  </CardTitle>
                  <CardDescription>
                    Upload relevant documents (PDF, DOCX, TXT) containing
                    support information, product details, FAQs, etc.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <label htmlFor="file-upload" className="sr-only">
                      Choose files
                    </label>
                    <Input
                      id="file-upload"
                      type="file"
                      multiple
                      onChange={handleFileChange}
                      className="cursor-pointer"
                      disabled={isLoading} // Disable while uploading
                      accept=".pdf,.docx,.txt" // Specify acceptable file types
                    />
                  </div>
                  {selectedFiles.length > 0 && (
                    <div className="text-sm text-muted-foreground space-y-1 max-h-32 overflow-y-auto border p-2 rounded-md">
                      {" "}
                      {/* Added scroll */}
                      <p className="font-medium">
                        Selected ({selectedFiles.length}):
                      </p>
                      <ul>
                        {selectedFiles.map((file, index) => (
                          <li key={index} className="truncate">
                            {file.name} ({(file.size / 1024).toFixed(1)} KB)
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <Button
                    onClick={handleUploadFiles}
                    disabled={selectedFiles.length === 0 || isLoading}
                    className="cursor-pointer"
                  >
                    {isLoading && selectedFiles.length > 0 ? ( // Show loading state on button
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />{" "}
                        Uploading...
                      </>
                    ) : (
                      "Upload Selected Files"
                    )}
                  </Button>
                </CardContent>
              </Card>

              {/* Section 2: Paste Text */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center">
                    <ClipboardPaste className="mr-2 h-5 w-5" /> Paste Text
                    Content
                  </CardTitle>
                  <CardDescription>
                    Paste text directly (e.g., from websites, emails). Give it a
                    descriptive title.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <label
                      htmlFor="content-title"
                      className="block text-sm font-medium mb-1"
                    >
                      Content Title <span className="text-red-500">*</span>
                    </label>
                    <Input
                      id="content-title"
                      value={pastedTitle}
                      onChange={(e) => setPastedTitle(e.target.value)}
                      placeholder="e.g., Website - Return Policy"
                      required
                      disabled={isLoading} // Disable while uploading/saving
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="pasted-content"
                      className="block text-sm font-medium mb-1"
                    >
                      Pasted Text <span className="text-red-500">*</span>
                    </label>
                    <Textarea
                      id="pasted-content"
                      value={pastedContent}
                      onChange={(e) => setPastedContent(e.target.value)}
                      placeholder="Paste your content here..."
                      rows={8}
                      required
                      disabled={isLoading} // Disable while uploading/saving
                    />
                  </div>
                  <Button
                    onClick={handleSavePastedText}
                    disabled={!pastedTitle || !pastedContent || isLoading}
                    className="cursor-pointer"
                  >
                    {isLoading &&
                    (!selectedFiles || selectedFiles.length === 0) ? ( // Show loading state if saving text
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />{" "}
                        Saving...
                      </>
                    ) : (
                      "Upload Pasted Text"
                    )}
                  </Button>
                </CardContent>
              </Card>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
