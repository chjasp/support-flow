"use client";

import React, { useRef, useState, useMemo } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Html } from '@react-three/drei';
import * as THREE from 'three';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
// Simple Badge component
const Badge = ({ 
  children, 
  variant = "default", 
  className = "", 
  onClick 
}: { 
  children: React.ReactNode; 
  variant?: "default" | "outline"; 
  className?: string; 
  onClick?: () => void; 
}) => (
  <span
    className={`inline-flex items-center px-2 py-1 rounded text-xs font-medium cursor-pointer ${
      variant === "default" 
        ? "bg-blue-500 text-white" 
        : "border border-gray-400 text-gray-300"
    } ${className}`}
    onClick={onClick}
  >
    {children}
  </span>
);

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

// Document data interface for 3D visualization
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
          color={isHighlighted ? '#ffff00' : document.color}
          emissive={hovered || isHovered || isHighlighted ? (isHighlighted ? '#ffff00' : document.color) : '#000000'}
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
  setAgents 
}: {
  agent: Agent;
  setAgents: React.Dispatch<React.SetStateAction<Agent[]>>;
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
  setAgents
}: {
  documents: Document3D[];
  onDocumentHover: (doc: Document3D | null) => void;
  onDocumentClick: (doc: Document3D) => void;
  hoveredDocument: Document3D | null;
  searchTerm: string;
  activeFilters: string[];
  agents: Agent[];
  setAgents: React.Dispatch<React.SetStateAction<Agent[]>>;
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

// Main DocumentCloud3D component
export default function DocumentCloud3D({ 
  documents = [],
  onDocumentSelect,
  agents = [],
  setAgents
}: {
  documents?: Document[];
  onDocumentSelect?: (doc: Document3D) => void;
  agents?: Agent[];
  setAgents?: React.Dispatch<React.SetStateAction<Agent[]>>;
}) {
  const [hoveredDocument, setHoveredDocument] = useState<Document3D | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [activeFilters, setActiveFilters] = useState<string[]>([]);

  // Generate document colors based on type/category
  const getDocumentColor = (doc: Document): string => {
    const colors = {
      'PDF': '#e74c3c',
      'DOCX': '#3498db', 
      'TXT': '#2ecc71',
      'Pasted Text': '#f39c12',
      'default': '#9b59b6'
    };
    return colors[doc.fileType as keyof typeof colors] || colors.default;
  };

  // Get available file types for filtering
  const availableFileTypes = useMemo(() => {
    const types = new Set<string>();
    documents.forEach(doc => {
      types.add(doc.fileType || doc.type);
    });
    return Array.from(types);
  }, [documents]);

  // Convert documents to 3D format with semantic positioning
  const documents3D = useMemo(() => {
    if (!documents || documents.length === 0) {
      // Generate sample data for demonstration
      return Array.from({ length: 20 }, (_, index) => ({
        id: `demo-${index}`,
        name: `Document ${index + 1}`,
        type: 'Document' as const,
        fileType: ['PDF', 'DOCX', 'TXT'][index % 3],
        position: [
          (Math.random() - 0.5) * 15,
          (Math.random() - 0.5) * 10,
          (Math.random() - 0.5) * 15
        ] as [number, number, number],
        color: ['#e74c3c', '#3498db', '#2ecc71'][index % 3],
        size: 0.3 + Math.random() * 0.4,
        dateAdded: new Date().toISOString(),
        status: 'Ready' as const
      }));
    }

    return documents.map((doc) => ({
      id: doc.id,
      name: doc.name,
      type: doc.type,
      fileType: doc.fileType,
      position: [
        // Semantic clustering simulation - in real implementation, 
        // this would be based on document embeddings
        (Math.random() - 0.5) * 15,
        (Math.random() - 0.5) * 10,
        (Math.random() - 0.5) * 15
      ] as [number, number, number],
      color: getDocumentColor(doc),
      size: 0.2 + Math.random() * 0.3,
      dateAdded: doc.dateAdded,
      status: (doc.status === 'Ready' || doc.status === 'Processing' || doc.status === 'Error') 
        ? doc.status 
        : 'Ready' as const
    }));
  }, [documents]);

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
        className="bg-gradient-to-b from-gray-900 to-black"
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
        />
      </Canvas>

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
        </div>
      )}


    </div>
  );
} 