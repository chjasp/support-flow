"use client";

import React, { useRef, useState, useMemo, useEffect } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Html } from '@react-three/drei';
import * as THREE from 'three';
import { useSession } from 'next-auth/react';

// Document interface matching the knowledge base
interface Document {
  id: string;
  name: string;
  type: "Document" | "Pasted Text" | "Web Page";
  fileType?: string;
  dateAdded: string;
  status: "Uploading" | "Processing" | "Ready" | "Error" | "Unknown";
  gcsUri?: string;
  uploadError?: string;
}

// Document data interface for 3D visualization
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
  url?: string; // For web pages
  chunkCount?: number;
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

// Individual document sphere component
function DocumentSphere({ 
  document, 
  onHover, 
  onClick, 
  isHovered, 
  isHighlighted,
  isFiltered 
}: {
  document: Document3D;
  onHover: (doc: Document3D | null) => void;
  onClick: (doc: Document3D) => void;
  isHovered: boolean;
  isHighlighted: boolean;
  isFiltered: boolean;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const [hovered, setHovered] = useState(false);

  // Animate the sphere
  useFrame((state) => {
    if (meshRef.current) {
      // Gentle floating animation
      meshRef.current.position.y = document.position[1] + Math.sin(state.clock.elapsedTime + document.position[0]) * 0.1;
      
      // Scale animation on hover or highlight
      const targetScale = (hovered || isHovered || isHighlighted) ? 1.3 : 1;
      meshRef.current.scale.lerp(new THREE.Vector3(targetScale, targetScale, targetScale), 0.1);
      
      // Pulse animation for highlighted documents
      if (isHighlighted) {
        const pulse = Math.sin(state.clock.elapsedTime * 3) * 0.1 + 1;
        meshRef.current.scale.setScalar(pulse * targetScale);
      }
    }
  });

  const handlePointerOver = () => {
    setHovered(true);
    onHover(document);
  };

  const handlePointerOut = () => {
    setHovered(false);
    onHover(null);
  };

  return (
    <group position={document.position}>
      <mesh
        ref={meshRef}
        onPointerOver={handlePointerOver}
        onPointerOut={handlePointerOut}
        onClick={() => onClick(document)}
        visible={!isFiltered}
      >
        <sphereGeometry args={[document.size, 32, 32]} />
        <meshStandardMaterial
          color={isHighlighted ? '#ffff00' : '#ffffff'}
          emissive={hovered || isHovered || isHighlighted ? (isHighlighted ? '#ffff00' : '#ffffff') : '#000000'}
          emissiveIntensity={(hovered || isHovered || isHighlighted) ? 0.3 : 0}
          opacity={isFiltered ? 0.2 : 1}
        />
      </mesh>
      
      {/* Document label */}
      {((hovered || isHovered || isHighlighted) && !isFiltered) && (
        <Html center>
          <div className={`px-2 py-1 rounded text-xs whitespace-nowrap pointer-events-none ${
            isHighlighted 
              ? 'bg-yellow-500/90 text-black font-semibold' 
              : 'bg-black/80 text-white'
          }`}>
            {document.name}
          </div>
        </Html>
      )}
    </group>
  );
}

// Individual agent sphere component
function AgentSphere({
  agent,
  setAgents,
  onAgentClick
}: {
  agent: Agent;
  setAgents: React.Dispatch<React.SetStateAction<Agent[]>>;
  onAgentClick: (agent: Agent) => void;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const [hovered, setHovered] = useState(false);

  // Animate the agent sphere
  useFrame((state) => {
    if (meshRef.current) {
      // Smooth movement towards target position
      const currentPos = new THREE.Vector3(...agent.position);
      const targetPos = new THREE.Vector3(...agent.targetPosition);
      
      // Lerp towards target position
      const lerpedPos = currentPos.lerp(targetPos, 0.02);
      meshRef.current.position.copy(lerpedPos);
      
      // Update agent position in state
      setAgents(prev => prev.map(a => 
        a.id === agent.id 
          ? { ...a, position: [lerpedPos.x, lerpedPos.y, lerpedPos.z] }
          : a
      ));
      
      // Gentle floating animation
      meshRef.current.position.y += Math.sin(state.clock.elapsedTime * 2 + agent.position[0]) * 0.05;
      
      // Pulsing animation when moving
      if (agent.status === 'moving') {
        const pulse = Math.sin(state.clock.elapsedTime * 4) * 0.1 + 1;
        meshRef.current.scale.setScalar(pulse);
      } else {
        meshRef.current.scale.setScalar(hovered ? 1.2 : 1);
      }
    }
  });

  return (
    <group>
      <mesh
        ref={meshRef}
        onPointerOver={() => setHovered(true)}
        onPointerOut={() => setHovered(false)}
        onClick={() => onAgentClick(agent)}
      >
        <sphereGeometry args={[0.4, 16, 16]} />
        <meshStandardMaterial
          color={agent.color}
          emissive={agent.color}
          emissiveIntensity={agent.status === 'moving' ? 0.5 : 0.3}
          opacity={1}
        />
      </mesh>
      
      {/* Agent label */}
      {hovered && (
        <Html center>
          <div className="px-2 py-1 rounded text-xs whitespace-nowrap pointer-events-none bg-black/80 text-white">
            {agent.name} ({agent.status})
          </div>
        </Html>
      )}
    </group>
  );
}

// Main 3D scene component
function Scene({
  documents,
  onDocumentHover,
  onDocumentClick,
  hoveredDocument,
  searchTerm,
  activeFilters,
  agents,
  setAgents,
  onAgentClick
}: {
  documents: Document3D[];
  onDocumentHover: (doc: Document3D | null) => void;
  onDocumentClick: (doc: Document3D) => void;
  hoveredDocument: Document3D | null;
  searchTerm: string;
  activeFilters: string[];
  agents: Agent[];
  setAgents: React.Dispatch<React.SetStateAction<Agent[]>>;
  onAgentClick: (agent: Agent) => void;
}) {
  // Filter and highlight logic
  const processedDocuments = useMemo(() => {
    return documents.map(doc => {
      const matchesSearch = searchTerm === '' || 
        doc.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (doc.fileType && doc.fileType.toLowerCase().includes(searchTerm.toLowerCase()));
      
      const matchesFilter = activeFilters.length === 0 || 
        activeFilters.includes(doc.fileType || doc.type);

      return {
        ...doc,
        isHighlighted: searchTerm !== '' && matchesSearch,
        isFiltered: !matchesFilter || (searchTerm !== '' && !matchesSearch)
      };
    });
  }, [documents, searchTerm, activeFilters]);

  return (
    <>
      {/* Lighting */}
      <ambientLight intensity={0.6} />
      <pointLight position={[10, 10, 10]} intensity={1} />
      <pointLight position={[-10, -10, -10]} intensity={0.5} />
      
      {/* Documents */}
      {processedDocuments.map((doc) => (
        <DocumentSphere
          key={doc.id}
          document={doc}
          onHover={onDocumentHover}
          onClick={onDocumentClick}
          isHovered={hoveredDocument?.id === doc.id}
          isHighlighted={doc.isHighlighted || false}
          isFiltered={doc.isFiltered || false}
        />
      ))}
      
      {/* Agents */}
      {agents.map((agent) => (
        <AgentSphere
          key={agent.id}
          agent={agent}
          setAgents={setAgents}
          onAgentClick={onAgentClick}
        />
      ))}
      
      {/* Camera controls */}
      <OrbitControls
        enablePan={true}
        enableZoom={true}
        enableRotate={true}
        maxDistance={30}
        minDistance={5}
      />
    </>
  );
}

// Hook to fetch 3D document data
function use3DDocuments() {
  const { data: session } = useSession();
  const [documents3D, setDocuments3D] = useState<Document3D[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchDocuments3D = async () => {
    if (!session?.idToken) return;

    setLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/web/documents-3d', {
        headers: {
          'Authorization': `Bearer ${session.idToken}`,
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch 3D documents: ${response.statusText}`);
      }

      const data = await response.json();
      
      // Transform backend data to frontend format
      const transformed = data.map((doc: any) => ({
        id: doc.id,
        name: doc.name,
        type: doc.type,
        fileType: doc.fileType,
        position: doc.position as [number, number, number],
        color: '#ffffff',
        size: Math.max(0.2, Math.min(0.8, (doc.chunkCount || 1) / 50)), // Size based on chunk count
        dateAdded: doc.dateAdded,
        status: doc.status,
        url: doc.url,
        chunkCount: doc.chunkCount
      }));

      setDocuments3D(transformed);
    } catch (err) {
      console.error('Error fetching 3D documents:', err);
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments3D();
  }, [session?.idToken]);

  return { documents3D, loading, error, refetch: fetchDocuments3D };
}

// Helper function to get colors by document type

// Main DocumentCloud3D component
export default function DocumentCloud3D({
  documents = [],
  onDocumentSelect,
  agents = [],
  setAgents,
  onAgentSelect
}: {
  documents?: Document[];
  onDocumentSelect?: (doc: Document3D) => void;
  agents?: Agent[];
  setAgents?: React.Dispatch<React.SetStateAction<Agent[]>>;
  onAgentSelect?: (agent: Agent) => void;
}) {
  const [hoveredDocument, setHoveredDocument] = useState<Document3D | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [activeFilters, setActiveFilters] = useState<string[]>([]);
  
  // Fetch real 3D document data
  const { documents3D: realDocuments3D, loading, error } = use3DDocuments();


  // Use real 3D data if available, otherwise fall back to converted documents
  const documents3D = useMemo(() => {
    // If we have real 3D data, use it
    if (realDocuments3D.length > 0) {
      return realDocuments3D.map(doc => ({ ...doc, color: '#ffffff' }));
    }

    // Otherwise, convert regular documents if available
    if (documents && documents.length > 0) {
      return documents.map((doc) => ({
        id: doc.id,
        name: doc.name,
        type: doc.type,
        fileType: doc.fileType,
        position: [
          // Random positioning for documents without 3D coordinates
          (Math.random() - 0.5) * 15,
          (Math.random() - 0.5) * 10,
          (Math.random() - 0.5) * 15
        ] as [number, number, number],
        color: '#ffffff',
        size: 0.2 + Math.random() * 0.3,
        dateAdded: doc.dateAdded,
        status: (doc.status === 'Ready' || doc.status === 'Processing' || doc.status === 'Error') 
          ? doc.status 
          : 'Ready' as const
      }));
    }

    // No data available
    return [];
  }, [realDocuments3D, documents]);

  // Get available file types for filtering
  const availableFileTypes = useMemo(() => {
    const types = new Set<string>();
    documents3D.forEach(doc => {
      types.add(doc.fileType || doc.type);
    });
    return Array.from(types);
  }, [documents3D]);

  const handleDocumentClick = (document: Document3D) => {
    console.log('Document clicked:', document);
    onDocumentSelect?.(document);
  };

  const toggleFilter = (fileType: string) => {
    setActiveFilters(prev => 
      prev.includes(fileType) 
        ? prev.filter(f => f !== fileType)
        : [...prev, fileType]
    );
  };

  const clearFilters = () => {
    setActiveFilters([]);
    setSearchTerm('');
  };

  // Calculate visible document count
  const visibleCount = useMemo(() => {
    return documents3D.filter(doc => {
      const matchesSearch = searchTerm === '' || 
        doc.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (doc.fileType && doc.fileType.toLowerCase().includes(searchTerm.toLowerCase()));
      
      const matchesFilter = activeFilters.length === 0 || 
        activeFilters.includes(doc.fileType || doc.type);

      return matchesFilter && (searchTerm === '' || matchesSearch);
    }).length;
  }, [documents3D, searchTerm, activeFilters]);

  return (
    <div className="w-full h-full relative">
      <Canvas
        camera={{ position: [10, 5, 10], fov: 75 }}
        className="bg-black"
      >
        <Scene
          documents={documents3D}
          onDocumentHover={setHoveredDocument}
          onDocumentClick={handleDocumentClick}
          hoveredDocument={hoveredDocument}
          searchTerm={searchTerm}
          activeFilters={activeFilters}
          agents={agents}
          setAgents={setAgents || (() => {})}
          onAgentClick={onAgentSelect || (() => {})}
        />
      </Canvas>

      {/* Loading indicator */}
      {loading && (
        <div className="absolute top-4 right-4 bg-black/80 text-white p-2 rounded">
          Loading 3D data...
        </div>
      )}

      {/* Error indicator */}
      {error && (
        <div className="absolute top-4 right-4 bg-red-500/80 text-white p-2 rounded max-w-xs">
          Error: {error}
        </div>
      )}

      {/* Hover information overlay */}
      {hoveredDocument && (
        <div className="absolute top-4 left-4 bg-black/80 text-white p-4 rounded-lg max-w-xs">
          <h3 className="font-semibold text-sm">{hoveredDocument.name}</h3>
          <p className="text-xs text-gray-300 mt-1">
            Type: {hoveredDocument.fileType || hoveredDocument.type}
          </p>
          <p className="text-xs text-gray-300">
            Status: {hoveredDocument.status}
          </p>
          <p className="text-xs text-gray-300">
            Added: {new Date(hoveredDocument.dateAdded).toLocaleDateString()}
          </p>
          {hoveredDocument.chunkCount && (
            <p className="text-xs text-gray-300">
              Chunks: {hoveredDocument.chunkCount}
            </p>
          )}
          {hoveredDocument.url && (
            <p className="text-xs text-blue-300 truncate">
              URL: {hoveredDocument.url}
            </p>
          )}
        </div>
      )}

      {/* Document count and controls removed for cleaner interface */}
    </div>
  );
} 