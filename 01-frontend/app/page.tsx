"use client";

import { useSession, signIn } from "next-auth/react";
import { Button } from "@/components/ui/button";
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
  type: 'Document' | 'Pasted Text';
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
  const [isLoading, setIsLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');

  // Agent state management
  const [agents, setAgents] = useState<Agent[]>([
    {
      id: 'oli',
      name: 'Oli',
      color: '#8B5CF6', // Purple
      position: [-8, 2, -8],
      targetPosition: [-8, 2, -8],
      status: 'idle',
      initialPosition: [-8, 2, -8]
    },
    {
      id: 'maxi',
      name: 'Maxi',
      color: '#10B981', // Green
      position: [0, 2, -10],
      targetPosition: [0, 2, -10],
      status: 'idle',
      initialPosition: [0, 2, -10]
    },
    {
      id: 'jannik',
      name: 'Jannik',
      color: '#F59E0B', // Orange
      position: [8, 2, -8],
      targetPosition: [8, 2, -8],
      status: 'idle',
      initialPosition: [8, 2, -8]
    }
  ]);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [isAgentChatOpen, setIsAgentChatOpen] = useState(false);
  const [agentInstruction, setAgentInstruction] = useState('');

  // Fetch documents from the knowledge base
  const fetchDocuments = useCallback(async () => {
    if (status !== "authenticated" || !session?.idToken) {
      return;
    }

    setIsLoading(true);
    try {
      const response = await fetch('/api/documents', {
        headers: {
          Authorization: `Bearer ${session.idToken}`,
        },
      });

      if (response.ok) {
        const data: Document[] = await response.json();
        setDocuments(data.filter(doc => doc.status === 'Ready')); // Only show ready documents
      } else {
        console.error('Failed to fetch documents:', response.statusText);
      }
    } catch (error) {
      console.error('Error fetching documents:', error);
    } finally {
      setIsLoading(false);
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

  // Handle agent selection
  const handleAgentSelect = (agent: Agent) => {
    setSelectedAgent(agent);
    setIsAgentChatOpen(true);
    setAgentInstruction('');
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
  const handleStartAgentTask = () => {
    if (!selectedAgent || !agentInstruction.trim()) return;

    // Generate 5 random waypoints
    const waypoints = generateRandomPositions(5);
    
    // Update agent status and start movement
    setAgents(prev => prev.map(agent => 
      agent.id === selectedAgent.id 
        ? { 
            ...agent, 
            status: 'moving' as const, 
            currentTask: agentInstruction.trim()
          }
        : agent
    ));

    // Close the chat modal
    setIsAgentChatOpen(false);
    setSelectedAgent(null);

    // Start the movement sequence
    moveAgentThroughWaypoints(selectedAgent.id, waypoints);
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
      />

      {/* Combined Control Panel */}
      <div className="absolute bottom-4 right-4 bg-black/90 text-white p-6 rounded-lg max-w-sm shadow-2xl shadow-black/50">
        {/* Search & Filter Section */}
        <div className="mb-6">
          <h3 className="font-semibold mb-3">Search & Filter</h3>
          
          {/* Search Input */}
          <input
            placeholder="Search documents..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full mb-3 px-3 py-2 text-white bg-gray-800 border border-gray-600 rounded-md placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />

          {/* File Type Filters */}
          <div className="mb-3">
            <p className="text-xs text-gray-300 mb-2">Filter by type:</p>
            <div className="flex flex-wrap gap-1">
              {documents.length > 0 && Array.from(new Set(documents.map(doc => doc.fileType || doc.type))).map(type => (
                <span
                  key={type}
                  className={`inline-flex items-center px-2 py-1 rounded text-xs font-medium cursor-pointer ${
                    false ? "bg-blue-500 text-white" : "border border-gray-400 text-gray-300"
                  }`}
                >
                  {type}
                </span>
              ))}
            </div>
          </div>

          {/* Results Count */}
          <p className="text-xs text-gray-400">
            Showing {documents.filter(doc => doc.status === 'Ready').length} ready documents
          </p>
        </div>

        {/* Divider */}
        <div className="border-t border-gray-700 mb-6"></div>

        {/* AI Agents Section */}
        <div>
          <h3 className="font-semibold mb-3 text-center">AI Agents</h3>
          <div className="space-y-2">
            {agents.map((agent) => (
              <div
                key={agent.id}
                onClick={() => handleAgentSelect(agent)}
                className="cursor-pointer p-3 rounded-lg border-2 transition-all hover:bg-white/10"
                style={{ borderColor: agent.color }}
              >
                <div className="flex items-center gap-3">
                  <div
                    className="w-4 h-4 rounded-full"
                    style={{ backgroundColor: agent.color }}
                  />
                  <div className="flex-1">
                    <p className="font-medium">{agent.name}</p>
                    <p className="text-xs text-gray-300 capitalize">{agent.status}</p>
                    {agent.currentTask && (
                      <p className="text-xs text-blue-300 mt-1 truncate">
                        {agent.currentTask}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Agent Chat Modal */}
      <Dialog open={isAgentChatOpen} onOpenChange={setIsAgentChatOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {selectedAgent && (
                <div
                  className="w-4 h-4 rounded-full"
                  style={{ backgroundColor: selectedAgent.color }}
                />
              )}
              Chat with {selectedAgent?.name}
            </DialogTitle>
            <DialogDescription>
              Give {selectedAgent?.name} a task to research in the document space.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <label htmlFor="instruction" className="text-sm font-medium">
                What would you like {selectedAgent?.name} to research?
              </label>
              <textarea
                id="instruction"
                placeholder="e.g., Find information about our pricing structure and competitive advantages"
                value={agentInstruction}
                onChange={(e) => setAgentInstruction(e.target.value)}
                className="min-h-[100px] px-3 py-2 border border-gray-300 rounded-md resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="flex gap-2">
              <Button
                onClick={handleStartAgentTask}
                disabled={!agentInstruction.trim()}
                className="flex-1"
              >
                🚀 Start Research
              </Button>
              <Button
                variant="outline"
                onClick={() => setIsAgentChatOpen(false)}
                className="flex-1"
              >
                Cancel
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

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
