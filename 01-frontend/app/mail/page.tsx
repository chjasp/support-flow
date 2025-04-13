import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { Separator } from "@/components/ui/separator";

export default function MailPage() {
  return (
    <div className="flex flex-col h-screen"> {/* Removed px-6, handle padding within panels */}
      {/* Page Header */}
      <div className="px-6"> {/* Add padding back for the header */}
        <h1 className="text-3xl font-bold tracking-tight my-6">Mail</h1>
        <p className="text-muted-foreground mt-2 mb-4"> {/* Added bottom margin */}
          Access your customer emails here.
        </p>
      </div>

      {/* Main Resizable Layout */}
      <ResizablePanelGroup
        direction="horizontal"
        className="flex-1 border rounded-lg" // Use flex-1 to fill remaining height, add border
      >
        {/* Left Pane: Inbox List */}
        <ResizablePanel defaultSize={25} minSize={20} maxSize={40}>
          <div className="flex flex-col h-full p-4">
            <h2 className="text-xl font-semibold mb-4">AI Inbox</h2>
            {/* Optional Filters Placeholder */}
            {/* <div className="mb-4">
              <button>Needs Review</button>
              <button>Handled</button>
            </div> */}
            <Separator className="mb-4" />
            {/* Email List Area Placeholder */}
            <div className="flex-1 overflow-auto">
              <p className="text-sm text-muted-foreground">Email list items will go here...</p>
              {/* Example List Item Structure (Placeholder) */}
              {/* <div className="p-2 border-b hover:bg-accent cursor-pointer">
                <p className="font-medium">Sender Name</p>
                <p className="text-sm truncate">Subject Line Goes Here</p>
                <p className="text-xs text-muted-foreground">Date/Time</p>
              </div> */}
            </div>
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Right Pane: Detail View */}
        <ResizablePanel defaultSize={75}>
          <ResizablePanelGroup direction="vertical">
            {/* Top Section: Incoming Email */}
            <ResizablePanel defaultSize={50} minSize={30}>
              <div className="flex flex-col h-full p-4">
                <h2 className="text-xl font-semibold mb-2">Received Email</h2>
                {/* Email Metadata Placeholder */}
                <div className="text-sm text-muted-foreground mb-4 border-b pb-2">
                  <p><strong>From:</strong> sender@example.com</p>
                  <p><strong>To:</strong> you@example.com</p>
                  <p><strong>Date:</strong> 2023-10-27 10:00 AM</p>
                  <p><strong>Subject:</strong> Original Email Subject</p>
                </div>
                {/* Email Body Viewer Placeholder */}
                <div className="flex-1 overflow-auto">
                  <p>Original email body content will be displayed here...</p>
                </div>
              </div>
            </ResizablePanel>

            <ResizableHandle withHandle />

            {/* Bottom Section: AI Reply Draft */}
            <ResizablePanel defaultSize={50} minSize={30}>
              <div className="flex flex-col h-full p-4">
                <h2 className="text-xl font-semibold mb-2">Suggested Reply (Editable Draft)</h2>
                {/* Optional Reply Subject Placeholder */}
                {/* <input type="text" value="Re: Original Email Subject" className="mb-2 p-1 border rounded" /> */}
                {/* Editable Text Area Placeholder */}
                <div className="flex-1 mb-4 border rounded p-2 overflow-auto bg-background">
                  <textarea
                    className="w-full h-full resize-none border-none outline-none bg-transparent"
                    placeholder="AI-generated reply draft will appear here..."
                  ></textarea>
                </div>
                {/* Action Toolbar Placeholder */}
                <div className="flex space-x-2 justify-end">
                  <button className="px-4 py-2 bg-primary text-primary-foreground rounded hover:bg-primary/90">
                    Copy Reply
                  </button>
                  <button className="px-4 py-2 border border-input bg-background hover:bg-accent hover:text-accent-foreground rounded">
                    Mark as Handled
                  </button>
                  {/* <button className="px-4 py-2 border border-destructive/50 text-destructive hover:bg-destructive/10 rounded">
                    Discard Draft
                  </button> */}
                </div>
              </div>
            </ResizablePanel>
          </ResizablePanelGroup>
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}
