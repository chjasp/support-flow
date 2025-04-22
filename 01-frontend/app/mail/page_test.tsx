"use client";

// Keep only essential imports for layout and basic elements
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable"; // Assuming these paths are correct
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Send } from "lucide-react"; // Keep for visual structure

// --- Dummy long text for testing ---
const longMessage = `
Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.
Curabitur pretium tincidunt lacus. Nulla gravida orci a odio. Nullam varius, turpis et commodo pharetra, est eros bibendum elit, nec luctus magna felis sollicitudin mauris. Integer in mauris eu nibh euismod gravida. Duis ac tellus et risus vulputate vehicula. Donec lobortis risus a elit. Etiam tempor. Ut ullamcorper, ligula eu tempor congue, eros est euismod turpis, id tincidunt sapien risus a quam. Maecenas fermentum consequat mi. Donec nec lacus eget lectus faucibus aliquam.
Suspendisse potenti. Cras in purus eu magna vulputate luctus. Cum sociis natoque penatibus et magnis dis parturient montes, nascetur ridiculus mus. Vivamus consectetuer hendrerit lacus. Mauris DORTincidunt, uma ac condimentum vestibulum, massa justo posuere risus, vitae
volutpat nibh metus eget pede. Cras non sem sem. Nullam elementum, turpis vel semper laoreet, neque lorem malesuada arcu, quis consequat augue nisl eu lectus. Pellentesque consectetuer
lacus eu justo. Donec odio. Cras urna. Donec at ante. In hac habitasse platea dictumst.
Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo. Nemo enim ipsam voluptatem quia voluptas sit aspernatur aut odit aut fugit, sed quia consequuntur magni dolores eos qui ratione voluptatem sequi nesciunt. Neque porro quisquam est, qui dolorem ipsum quia dolor sit amet, consectetur, adipisci velit, sed quia non numquam eius modi tempora incidunt ut labore et dolore magnam aliquam quaerat voluptatem.
`;

export default function MailTestPage() {
  return (
    // Calculate height: 100vh - header height (h-14) - main padding-top (pt-6)
    // Keep flex-col and padding p-4
    <div className="flex flex-col p-4 h-[calc(100vh-theme(space.14)-theme(space.6))]">

      <h1 className="text-xl font-bold mb-4">Right Panel Scroll Test</h1>

      {/* Main Resizable Layout - Use flex-1 to fill the calculated height of the parent */}
      <ResizablePanelGroup
        direction="horizontal"
        className="flex-1 border rounded-lg" // Use flex-1, remove h-full
      >
        {/* Left Pane: Placeholder */}
        <ResizablePanel defaultSize={25} minSize={15}>
          <div className="flex h-full items-center justify-center p-6">
            <span className="font-semibold">Left Pane</span>
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Middle Pane: Placeholder */}
        <ResizablePanel defaultSize={45} minSize={30}>
          <div className="flex h-full items-center justify-center p-6">
            <span className="font-semibold">Middle Pane</span>
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Right Pane: Structure remains the same, scrolling should work */}
        <ResizablePanel defaultSize={30} minSize={20}>
          <div className="flex flex-col h-full">
            {/* Header */}
            <h2 className="text-lg font-semibold border-b pb-2 px-4 pt-4 flex-shrink-0">
              Chat Scroll Test
            </h2>
            {/* Scrollable Area */}
            <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4">
              <div className="space-y-3">
                {/* Messages */}
                <div className="p-2 rounded-lg max-w-[85%] bg-muted mr-auto">
                  <p className="text-sm whitespace-pre-wrap break-words">
                    <strong>Message 1:</strong> {longMessage}
                  </p>
                </div>
                <div className="p-2 rounded-lg max-w-[85%] bg-primary text-primary-foreground ml-auto">
                  <p className="text-sm whitespace-pre-wrap break-words">
                    <strong>Message 2:</strong> {longMessage}
                  </p>
                </div>
              </div>
            </div>
            {/* Input Area */}
            <div className="flex items-center gap-2 border-t px-4 py-3 flex-shrink-0">
              <Input
                placeholder="Test input..."
                className="flex-1"
              />
              <Button size="icon" disabled>
                <Send className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}