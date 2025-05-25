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
  RefreshCw,
  Globe,
} from "lucide-react"; // Example icons
import { useSession } from "next-auth/react"; // Import useSession
import { authFetch } from "@/lib/authFetch";

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



// --- Define Backend URLs (Use Environment Variables in production) ---
const GENERATE_UPLOAD_URL_ENDPOINT = "/api/generate-upload-url"; // Next.js API route
const GET_ITEMS_ENDPOINT = '/api/documents'; // Use relative path
const DELETE_ITEM_ENDPOINT = '/api/documents'; // Use relative path (base)
const ITEMS_PER_PAGE = 10; // Define items per page for pagination

export default function KnowledgeBasePage() {
  const { data: session, status } = useSession(); // Get session
  const [activeView, setActiveView] = useState<"overview" | "upload">(
    "overview"
  );
  const [knowledgeItems, setKnowledgeItems] = useState<KnowledgeItem[]>([]); // Start empty
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [pastedTitle, setPastedTitle] = useState("");
  const [pastedContent, setPastedContent] = useState("");
  const [urlList, setUrlList] = useState("");
  const [urlDescription, setUrlDescription] = useState("");
  const [isProcessingUrls, setIsProcessingUrls] = useState(false);
  const [isLoading, setIsLoading] = useState(false); // Loading state for uploads/saves
  const [isFetchingItems, setIsFetchingItems] = useState(true); // Keep initial loading state
  const [currentPage, setCurrentPage] = useState(1); // Add state for current page

  // --- Pagination Calculations ---
  const totalPages = Math.ceil(knowledgeItems.length / ITEMS_PER_PAGE);
  const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
  const endIndex = startIndex + ITEMS_PER_PAGE;
  const currentItems = knowledgeItems.slice(startIndex, endIndex);

  // --- Fetch Data Logic (extracted) ---
  const fetchKnowledgeItems = useCallback(async () => {
    // Only fetch if authenticated and session has idToken
    if (status !== "authenticated" || !session?.idToken) {
      console.log("Not authenticated or missing token, skipping fetch.");
      setIsFetchingItems(false); // Stop loading indicator
      setKnowledgeItems([]); // Clear items if not logged in
      return;
    }

    // Don't set isFetchingItems to true if only polling in the background,
    // unless it's the very first load. Let the Refresh button handle explicit loading state.
    // We can check if knowledgeItems is empty for the initial load.
    const isInitialLoad = knowledgeItems.length === 0;
    if (isInitialLoad) {
        setIsFetchingItems(true);
    }

    try {
      const response = await authFetch(session, GET_ITEMS_ENDPOINT);
      if (!response.ok) {
         if (response.status !== 401 && response.status !== 403) {
            throw new Error(`Failed to fetch items: ${response.statusText}`);
         }
         // If unauthorized, clear items and stop
         setKnowledgeItems([]);
         return; // Stop execution here for auth errors
      }

      const backendData: KnowledgeItem[] = await response.json();

      // --- Merging Logic ---
      setKnowledgeItems((prevItems) => {
        // 1. Identify temporary items still marked as "Uploading" in the previous state
        //    These items have a gcsUri because the upload attempt was made.
        const uploadingItems = prevItems.filter(
          (item) => item.status === "Uploading" && item.gcsUri
        );

        // 2. Create a map of backend items by gcsUri for efficient lookup.
        //    The backend needs to return gcsUri (original_gcs) for this to work.
        const backendDataMap = new Map(
          backendData
            .filter(item => item.gcsUri) // Only map items that have a gcsUri from backend
            .map((item) => [item.gcsUri, item])
        );

        // 3. Filter uploading items: keep only those whose gcsUri is NOT yet present in the backend response
        const pendingUploadItems = uploadingItems.filter(
          (item) => !backendDataMap.has(item.gcsUri)
        );

        // 4. Combine the fresh backend data with the pending temporary items
        const combinedItems = [...backendData, ...pendingUploadItems];

        // 5. Sort the combined list by dateAdded descending
        //    Ensure dateAdded is comparable (using full ISO string is better)
        combinedItems.sort((a, b) => new Date(b.dateAdded).getTime() - new Date(a.dateAdded).getTime());

        // console.log(`Merged items: ${backendData.length} from backend, ${pendingUploadItems.length} pending uploads kept.`);
        return combinedItems;
      });
      // --- End Merging Logic ---

    } catch (error) {
      console.error("Error fetching knowledge items:", error);
      // Keep existing items on fetch error? Or clear them? Decide based on desired UX.
      // For now, we keep them, but stop the loading indicator.
      // setKnowledgeItems([]); // Optionally clear items on error
    } finally {
      // Always set fetching to false after attempt, even if only polling
      setIsFetchingItems(false);
    }
  }, [status, session, knowledgeItems.length]); // Add knowledgeItems.length to detect initial load state change

  // --- Initial Data Fetch ---
  useEffect(() => {
    fetchKnowledgeItems();
  }, [fetchKnowledgeItems]); // fetchKnowledgeItems includes status/session dependency

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
        fetchKnowledgeItems(); // Fetch updates, not initial load
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
  }, [knowledgeItems, fetchKnowledgeItems]); // Re-run effect if items or fetchItems change

  // --- Event Handlers ---

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) {
      setSelectedFiles(Array.from(event.target.files));
    }
  };

  // --- Pagination Handlers ---
  const handlePreviousPage = () => {
    setCurrentPage((prev) => Math.max(prev - 1, 1)); // Ensure page doesn't go below 1
  };

  const handleNextPage = () => {
    setCurrentPage((prev) => Math.min(prev + 1, totalPages)); // Ensure page doesn't exceed totalPages
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
    // await fetchKnowledgeItems(); // You might need to extract fetchKnowledgeItems to be callable here
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
        } catch { /* Ignore if can't read text */ }
        throw new Error(gcsErrorDetails);
      }
      console.log(`Successfully uploaded text content as ${filename} to ${gcsUri}`);

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

  const handleProcessUrls = async () => {
    const urls = urlList
      .split("\n")
      .map((u) => u.trim())
      .filter((u) => u);
    if (urls.length === 0) {
      alert("Please enter one or more URLs.");
      return;
    }

    setIsProcessingUrls(true);
    try {
      const response = await authFetch(session, "/api/web/process-urls", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ urls, description: urlDescription }),
      });

      if (!response.ok) {
        let errorText = await response.text();
        throw new Error(
          `Failed to process URLs: ${response.status} ${response.statusText} ${errorText}`
        );
      }

      const data = await response.json();
      alert(
        data.message ||
          `Started processing ${urls.length} URL(s). They will appear once ready.`
      );
      setUrlList("");
      setUrlDescription("");
    } catch (error) {
      console.error("Error processing URLs:", error);
      const message = error instanceof Error ? error.message : String(error);
      alert(`Error processing URLs: ${message}`);
    } finally {
      setIsProcessingUrls(false);
    }
  };

  const handleDeleteItem = async (id: string, name: string) => {
    // 1. Find the item in the current state
    const itemToDelete = knowledgeItems.find(item => item.id === id);
    if (!itemToDelete) {
        console.warn("Item to delete not found in current state:", id);
        return; // Should not happen if button is clicked on an existing item
    }

    // 2. Check if it's a purely client-side error state (failed before backend processing)
    // We can infer this if the status is 'Error' and there's an 'uploadError' message,
    // indicating the failure likely happened during the frontend upload steps.
    // Alternatively, check if gcsUri is missing, as it's usually set after successful upload.
    const isClientSideFailure = itemToDelete.status === 'Error' && !!itemToDelete.uploadError;
    // const isClientSideFailure = itemToDelete.status === 'Error' && !itemToDelete.gcsUri; // Alternative check

    // 3. Confirmation Dialog (Keep this)
    if (!window.confirm(`Are you sure you want to delete "${name}"? This action cannot be undone.`)) {
      return; // Stop if user cancels
    }

    console.log(`Attempting to delete item: ${id}. Client-side failure: ${isClientSideFailure}`);

    // 4. Optimistic UI update: Remove the item immediately (applies to both cases)
    setKnowledgeItems((prev) => prev.filter((item) => item.id !== id));
    setCurrentPage(1); // Reset to first page after deleting an item

    // 5. If it wasn't a client-side failure, proceed with backend deletion
    if (!isClientSideFailure) {
      try {
        // Ensure session and idToken are available before making the call
        if (!session?.idToken) {
          console.error("No session token found. Cannot delete item.");
          alert("Authentication error. Please try logging in again.");
          // Rollback optimistic UI update
          setKnowledgeItems((prev) => [itemToDelete, ...prev].sort((a, b) => new Date(b.dateAdded).getTime() - new Date(a.dateAdded).getTime()));
          return;
        }

        const response = await authFetch(session, `${DELETE_ITEM_ENDPOINT}/${id}`, {
          method: "DELETE",
        });

        // Handle Backend Response
        if (!response.ok) {
          // If the response status code is not 2xx (e.g., 404, 500)
          let errorDetails = `Status: ${response.status} ${response.statusText}`;
          try {
              const errorData = await response.json();
              errorDetails += ` - ${errorData.detail || JSON.stringify(errorData)}`;
          } catch { // Removed unused 'parseError' variable
              try {
                  const errorText = await response.text();
                  errorDetails += ` - ${errorText || 'No further details'}`;
              } catch { /* Ignore */ } // Removed unused 'textError' variable
          }
          throw new Error(`Failed to delete item from backend: ${errorDetails}`);
        }

        // Success!
        console.log(`Successfully deleted item ID: ${id} from backend.`);
        // Optional: Show success notification

      } catch (error) {
        console.error("Error deleting item from backend:", error);

        // Rollback UI update on backend error
        setKnowledgeItems((prev) => [itemToDelete, ...prev].sort((a, b) => new Date(b.dateAdded).getTime() - new Date(a.dateAdded).getTime()));

        // Show error message to user
        const errorMessage = error instanceof Error ? error.message : String(error);
        alert(`Failed to delete "${name}" from backend.\nError: ${errorMessage}`);
      }
    } else {
        // If it *was* a client-side failure, we already removed it from the UI.
        // No backend call needed. Log success for local removal.
        console.log(`Successfully removed client-side item ID: ${id} (upload failed previously).`);
        // Optional: Show success notification for local removal
    }
    // Optional: Add a finally block if needed
  };

  return (
    <div className="flex h-[calc(100vh-theme(space.14)-theme(space.6))] w-full bg-background">
      {" "}
      {/* Adjust height based on header AND layout padding, add w-full */}
      {/* Sidebar */}
      <aside className="w-64 border-r p-4 flex flex-col space-y-2 overflow-y-auto">
        <h2 className="text-xl font-semibold mb-4">Knowledge Base</h2>
        <Button
          variant={activeView === "overview" ? "secondary" : "ghost"}
          className="justify-start cursor-pointer"
          onClick={() => setActiveView("overview")}
        >
          <FileText className="mr-2 h-4 w-4" /> Overview
        </Button>
        <Button
          variant={activeView === "upload" ? "secondary" : "ghost"}
          className="justify-start cursor-pointer"
          onClick={() => setActiveView("upload")}
        >
          <FileUp className="mr-2 h-4 w-4" /> Upload
        </Button>
      </aside>
      {/* Main Content Area */}
      <main className="flex-1 p-6 overflow-auto">
        {activeView === "overview" && (
          <div>
            <div className="flex justify-between items-center mb-2"> {/* Flex container for title and button */}
              <h1 className="text-3xl font-bold tracking-tight">
                Knowledge Base Overview
              </h1>
              <Button
                variant="outline"
                size="sm"
                onClick={fetchKnowledgeItems} // Call fetch function on click
                disabled={isFetchingItems} // Disable button while fetching
                className="cursor-pointer"
              >
                {isFetchingItems ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="mr-2 h-4 w-4" /> // Add refresh icon
                )}
                Refresh
              </Button>
            </div>
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
                      <TableRow key="loading-row">
                        <TableCell colSpan={5} className="text-center h-24">
                          <Loader2 className="h-6 w-6 animate-spin inline-block mr-2" />{" "}
                          Loading items...
                        </TableCell>
                      </TableRow>
                    ) : knowledgeItems.length > 0 ? (
                      currentItems.map((item) => (
                        <TableRow key={item.id}>
                          <TableCell className="font-medium">
                            {item.name}
                          </TableCell>
                          <TableCell>
                            {item.type === "Document"
                              ? `Doc (${item.fileType || "?"})`
                              : "Text"}
                          </TableCell>
                          <TableCell>
                            {item.dateAdded.split("T")[0]}
                          </TableCell>
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
                          {/* Update empty message check */}
                          {knowledgeItems.length === 0 ? "No knowledge items found. Add some!" : "No items on this page."}
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>

            {/* Pagination Controls */}
            {totalPages > 1 && ( // Only show pagination if there's more than one page
              <div className="flex items-center justify-end space-x-2 py-4">
                <span className="text-sm text-muted-foreground">
                  Page {currentPage} of {totalPages}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handlePreviousPage}
                  disabled={currentPage === 1}
                  className="cursor-pointer"
                >
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleNextPage}
                  disabled={currentPage === totalPages}
                  className="cursor-pointer"
                >
                  Next
                </Button>
              </div>
            )}
          </div>
        )}

        {activeView === "upload" && (
          <div>
            <h1 className="text-3xl font-bold tracking-tight mb-6">
              Add to Knowledge Base
            </h1>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
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

              {/* Section 3: Import URLs */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center">
                    <Globe className="mr-2 h-5 w-5" /> Add URLs
                  </CardTitle>
                  <CardDescription>
                    Provide one or more URLs to scrape and add to the knowledge base.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <label htmlFor="url-list" className="block text-sm font-medium mb-1">
                      URLs <span className="text-red-500">*</span>
                    </label>
                    <Textarea
                      id="url-list"
                      value={urlList}
                      onChange={(e) => setUrlList(e.target.value)}
                      placeholder="https://example.com/page1\nhttps://example.com/page2"
                      rows={4}
                      required
                      disabled={isProcessingUrls}
                      className="max-h-32 resize-none overflow-y-auto"
                    />
                  </div>
                  <div>
                    <label htmlFor="url-description" className="block text-sm font-medium mb-1">
                      Description
                    </label>
                    <Input
                      id="url-description"
                      value={urlDescription}
                      onChange={(e) => setUrlDescription(e.target.value)}
                      placeholder="Optional description"
                      disabled={isProcessingUrls}
                    />
                  </div>
                  <Button
                    onClick={handleProcessUrls}
                    disabled={isProcessingUrls || urlList.trim() === ""}
                    className="cursor-pointer"
                  >
                    {isProcessingUrls ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Processing...
                      </>
                    ) : (
                      "Process URLs"
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
