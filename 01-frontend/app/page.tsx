"use client";

import { useSession, signIn } from "next-auth/react";
import { authFetch } from "@/lib/authFetch";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loader2 } from "lucide-react";
import { useState, useEffect, useCallback } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { format } from "date-fns";
import DocumentCloud3D from "@/components/DocumentCloud3D";

// Document interface matching the knowledge base
interface Document {
  id: string;
  name: string;
  type: "Document" | "Pasted Text";
  fileType?: string;
  dateAdded: string;
  status: "Uploading" | "Processing" | "Ready" | "Error" | "Unknown";
  gcsUri?: string;
  uploadError?: string;
}

// 3D Document interface for the selected document
interface Document3D {
  id: string;
  name: string;
  type: 'Document' | 'Pasted Text' | 'Web Page';
  fileType?: string;
  position: [number, number, number];
  color: string;
  size: number;
  content?: string;
  dateAdded: string;
  status: 'Ready' | 'Processing' | 'Error';
}

// Agent interface for autonomous agents
interface Agent {
  id: string;
  name: string;
  color: string;
  position: [number, number, number];
  targetPosition: [number, number, number];
  status: 'idle' | 'moving' | 'researching' | 'thinking';
  currentTask?: string;
  initialPosition: [number, number, number];
}

export default function HomePage() {
  const { data: session, status } = useSession();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [selectedDocument, setSelectedDocument] = useState<Document3D | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Agent state management
  const [agents, setAgents] = useState<Agent[]>([
    {
      id: 'oli',
      name: 'Oli',
      color: '#1FBD54',
      position: [-8, 2, -8],
      targetPosition: [-8, 2, -8],
      status: 'idle',
      initialPosition: [-8, 2, -8]
    },
    {
      id: 'maxi',
      name: 'Maxi',
      color: '#3477F5',
      position: [0, 2, -10],
      targetPosition: [0, 2, -10],
      status: 'idle',
      initialPosition: [0, 2, -10]
    },
    {
      id: 'jannik',
      name: 'Jannik',
      color: '#E74E0F',
      position: [8, 2, -8],
      targetPosition: [8, 2, -8],
      status: 'idle',
      initialPosition: [8, 2, -8]
    }
  ]);
  const [agentInstruction, setAgentInstruction] = useState('');
  const [activeAgentId, setActiveAgentId] = useState('maxi');

  // Fetch documents from the knowledge base
  const fetchDocuments = useCallback(async () => {
    if (status !== "authenticated" || !session?.idToken) {
      return;
    }

    try {
      const response = await authFetch(session, '/api/documents');

      if (response.ok) {
        const data: Document[] = await response.json();
        setDocuments(data.filter(doc => doc.status === 'Ready'));
      } else {
        if (response.status !== 401 && response.status !== 403) {
          console.error('Failed to fetch documents:', response.statusText);
        }
      }
    } catch (error) {
      console.error('Error fetching documents:', error);
    }
  }, [status, session]);

  // Load documents on component mount
  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  // Handle document selection from 3D view
  const handleDocumentSelect = (document: Document3D) => {
    setSelectedDocument(document);
    setIsModalOpen(true);
  };

  // Handle chat with document
  const handleChatWithDocument = () => {
    if (selectedDocument) {
      // Navigate to chat with document context
      window.location.href = `/chat?document=${selectedDocument.id}`;
    }
  };


  // Generate random positions for agent movement
  const generateRandomPositions = (count: number): [number, number, number][] => {
    const positions: [number, number, number][] = [];
    for (let i = 0; i < count; i++) {
      positions.push([
        (Math.random() - 0.5) * 15,
        (Math.random() - 0.5) * 8 + 2,
        (Math.random() - 0.5) * 15
      ]);
    }
    return positions;
  };

  // Start agent task with movement
  const handleStartAgentTask = (agentId: string) => {
    if (!agentInstruction.trim()) return;

    // Generate 5 random waypoints
    const waypoints = generateRandomPositions(5);

    // Update agent status and start movement
    setAgents(prev => prev.map(agent =>
      agent.id === agentId
        ? {
            ...agent,
            status: 'moving' as const,
            currentTask: agentInstruction.trim()
          }
        : agent
    ));

    // Start the movement sequence
    moveAgentThroughWaypoints(agentId, waypoints);

    // Clear input after sending
    setAgentInstruction('');
  };

  // Move agent through waypoints and back to initial position
  const moveAgentThroughWaypoints = async (agentId: string, waypoints: [number, number, number][]) => {
    const allWaypoints = [...waypoints];
    
    // Add initial position at the end to return
    const agent = agents.find(a => a.id === agentId);
    if (agent) {
      allWaypoints.push(agent.initialPosition);
    }

    for (let i = 0; i < allWaypoints.length; i++) {
      const targetPos = allWaypoints[i];
      
      // Update target position
      setAgents(prev => prev.map(a => 
        a.id === agentId 
          ? { ...a, targetPosition: targetPos }
          : a
      ));

      // Wait for movement (2 seconds per waypoint)
      await new Promise(resolve => setTimeout(resolve, 2000));
    }

    // Mark task as complete
    setAgents(prev => prev.map(a => 
      a.id === agentId 
        ? { 
            ...a, 
            status: 'idle' as const, 
            currentTask: undefined,
            position: a.initialPosition,
            targetPosition: a.initialPosition
          }
        : a
    ));
  };

  /* ---------------- loading / auth gates ----------------- */
  if (status === "loading") {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (status === "unauthenticated") {
    return (
      <div className="flex flex-col items-center justify-center h-full">
        <p className="text-lg mb-4">Please sign in to continue.</p>
        <Button onClick={() => signIn("google")}>Sign In with Google</Button>
      </div>
    );
  }

  /* --------------------- 3D visualization ---------------------------- */
  return (
    <div className="absolute inset-0 top-14">

      {/* 3D Document Visualization */}
      <DocumentCloud3D
        documents={documents}
        onDocumentSelect={handleDocumentSelect}
        agents={agents}
        setAgents={setAgents}
        onAgentSelect={(agent) => setActiveAgentId(agent.id)}
      />

      {/* Agent interaction bar */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 w-[90%] max-w-xl flex items-center gap-2 bg-black/80 text-white p-2 rounded-lg">
        <select
          value={activeAgentId}
          onChange={(e) => setActiveAgentId(e.target.value)}
          className="bg-gray-800 text-white px-2 py-1 rounded-md"
        >
          {agents.map((agent) => (
            <option key={agent.id} value={agent.id}>
              {agent.name}
            </option>
          ))}
        </select>
        <Input
          placeholder="Ask the agent..."
          value={agentInstruction}
          onChange={(e) => setAgentInstruction(e.target.value)}
          className="flex-1"
        />
        <Button
          size="icon"
          onClick={() => handleStartAgentTask(activeAgentId)}
          disabled={!agentInstruction.trim()}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="currentColor"
            className="w-5 h-5"
          >
            <path d="M3.478 2.404a.75.75 0 0 0-.926.941l2.432 7.905H13.5a.75.75 0 0 1 0 1.5H4.984l-2.432 7.905a.75.75 0 0 0 .926.94 60.519 60.519 0 0 0 18.445-8.986.75.75 0 0 0 0-1.218A60.517 60.517 0 0 0 3.478 2.404Z" />
          </svg>
          <span className="sr-only">Send</span>
        </Button>
      </div>

      {/* Document Details Modal */}
      <Dialog open={isModalOpen} onOpenChange={setIsModalOpen}>
        <DialogContent className="sm:max-w-[600px]">
          <DialogHeader>
            <DialogTitle>Document Details</DialogTitle>
            <DialogDescription>
              Information about the selected document.
            </DialogDescription>
          </DialogHeader>
          {selectedDocument && (
            <div className="grid gap-4 py-4">
              <div className="grid grid-cols-4 items-center gap-4">
                <span className="text-right font-medium">Name:</span>
                <span className="col-span-3 font-mono text-sm">{selectedDocument.name}</span>
              </div>
              <div className="grid grid-cols-4 items-center gap-4">
                <span className="text-right font-medium">Type:</span>
                <span className="col-span-3">
                  {selectedDocument.fileType || selectedDocument.type}
                </span>
              </div>
              <div className="grid grid-cols-4 items-center gap-4">
                <span className="text-right font-medium">Status:</span>
                <span className="col-span-3">
                  <span className={`px-2 py-1 rounded text-xs ${
                    selectedDocument.status === 'Ready' 
                      ? 'bg-green-100 text-green-800'
                      : selectedDocument.status === 'Processing'
                      ? 'bg-yellow-100 text-yellow-800'
                      : 'bg-red-100 text-red-800'
                  }`}>
                    {selectedDocument.status}
                  </span>
                </span>
              </div>
              <div className="grid grid-cols-4 items-center gap-4">
                <span className="text-right font-medium">Added:</span>
                <span className="col-span-3">
                  {format(new Date(selectedDocument.dateAdded), "PPP p")}
                </span>
              </div>
              <div className="grid grid-cols-4 items-center gap-4">
                <span className="text-right font-medium">Position:</span>
                <span className="col-span-3 text-xs font-mono">
                  ({selectedDocument.position[0].toFixed(2)}, {selectedDocument.position[1].toFixed(2)}, {selectedDocument.position[2].toFixed(2)})
                </span>
              </div>
              
              {/* Action buttons */}
              <div className="flex gap-2 mt-4">
                <Button onClick={handleChatWithDocument} className="flex-1">
                  💬 Chat about this document
                </Button>
                <Button
                  variant="outline"
                  onClick={() => window.location.href = '/knowledge-base'}
                  className="flex-1"
                >
                  📁 View in Upload
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
