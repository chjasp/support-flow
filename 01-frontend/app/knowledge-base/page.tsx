'use client'; // Add this directive for using state and effects

import React, { useState } from 'react';
import { Button } from '@/components/ui/button'; // Assuming you use shadcn/ui
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Trash2, FileText, FileUp, ClipboardPaste } from 'lucide-react'; // Example icons

// Define a type for knowledge items (replace with your actual data structure)
type KnowledgeItem = {
  id: string;
  name: string;
  type: 'Document' | 'Pasted Text';
  fileType?: string; // e.g., 'PDF', 'DOCX'
  dateAdded: string; // Use string for simplicity, Date object is better
  status: 'Processing' | 'Ready' | 'Error';
};

// Placeholder data - replace with actual data fetching
const placeholderItems: KnowledgeItem[] = [
  { id: '1', name: 'faq.pdf', type: 'Document', fileType: 'PDF', dateAdded: '2023-10-27', status: 'Ready' },
  { id: '2', name: 'Website - Return Policy', type: 'Pasted Text', dateAdded: '2023-10-26', status: 'Processing' },
  { id: '3', name: 'onboarding.docx', type: 'Document', fileType: 'DOCX', dateAdded: '2023-10-25', status: 'Error' },
  { id: '4', name: 'support_scripts.txt', type: 'Document', fileType: 'TXT', dateAdded: '2023-10-24', status: 'Ready' },
];


export default function KnowledgeBasePage() {
  const [activeView, setActiveView] = useState<'overview' | 'upload'>('overview');
  const [knowledgeItems, setKnowledgeItems] = useState<KnowledgeItem[]>(placeholderItems); // State for items
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [pastedTitle, setPastedTitle] = useState('');
  const [pastedContent, setPastedContent] = useState('');

  // --- Event Handlers ---

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) {
      setSelectedFiles(Array.from(event.target.files));
      // TODO: Add visual feedback for selected files
    }
  };

  const handleUploadFiles = () => {
    console.log('Uploading files:', selectedFiles);
    // TODO: Implement actual file upload logic
    // TODO: Update knowledgeItems state with processing status
    // TODO: Show progress indicators
    alert(`Simulating upload for ${selectedFiles.length} file(s). Check console.`);
    setSelectedFiles([]); // Clear selection after "upload"
  };

  const handleSavePastedText = () => {
    if (!pastedTitle || !pastedContent) {
        alert('Please provide both a title and content.');
        return;
    }
    console.log('Saving pasted text:', { title: pastedTitle, content: pastedContent });
    // TODO: Implement actual saving logic
    // TODO: Update knowledgeItems state with processing status
    alert(`Simulating save for text titled "${pastedTitle}". Check console.`);
    // Add to list optimistically (or after successful save)
    const newItem: KnowledgeItem = {
        id: crypto.randomUUID(), // Generate temporary ID
        name: pastedTitle,
        type: 'Pasted Text',
        dateAdded: new Date().toISOString().split('T')[0], // Today's date
        status: 'Processing', // Start as processing
    };
    setKnowledgeItems(prev => [newItem, ...prev]);
    setPastedTitle('');
    setPastedContent('');
  };

  const handleDeleteItem = (id: string) => {
    console.log('Deleting item:', id);
    // TODO: Implement actual delete logic (API call)
    setKnowledgeItems(prev => prev.filter(item => item.id !== id));
    alert(`Simulating delete for item ID: ${id}.`);
  };


  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside className="w-64 border-r p-4 flex flex-col space-y-2">
        <h2 className="text-xl font-semibold mb-4">Knowledge Base</h2>
        <Button
          variant={activeView === 'overview' ? 'secondary' : 'ghost'}
          className="justify-start"
          onClick={() => setActiveView('overview')}
        >
          <FileText className="mr-2 h-4 w-4" /> Overview
        </Button>
        <Button
          variant={activeView === 'upload' ? 'secondary' : 'ghost'}
          className="justify-start"
          onClick={() => setActiveView('upload')}
        >
          <FileUp className="mr-2 h-4 w-4" /> Upload / Add
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
        {activeView === 'overview' && (
          <div>
            <h1 className="text-3xl font-bold tracking-tight mb-2">Knowledge Base Overview</h1>
            <p className="text-muted-foreground mb-6">
              View and manage your knowledge base articles and documents.
            </p>

            {/* Optional Search Bar */}
            <div className="mb-4">
              <Input type="search" placeholder="Search by name or title..." className="max-w-sm" />
            </div>

            {/* Knowledge Items List/Table */}
            <Card>
              <CardContent className="p-0"> {/* Remove padding for full-width table */}
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Name/Title</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Date Added</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {knowledgeItems.length > 0 ? (
                      knowledgeItems.map((item) => (
                        <TableRow key={item.id}>
                          <TableCell className="font-medium">{item.name}</TableCell>
                          <TableCell>
                            {item.type === 'Document' ? `Doc (${item.fileType || '?'})` : 'Text'}
                          </TableCell>
                          <TableCell>{item.dateAdded}</TableCell>
                          <TableCell>
                             <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                                item.status === 'Ready' ? 'bg-green-100 text-green-800' :
                                item.status === 'Processing' ? 'bg-yellow-100 text-yellow-800' :
                                item.status === 'Error' ? 'bg-red-100 text-red-800' :
                                'bg-gray-100 text-gray-800' // Default/fallback
                             }`}>
                                {item.status}
                             </span>
                          </TableCell>
                          <TableCell className="text-right">
                            <Button variant="ghost" size="icon" onClick={() => handleDeleteItem(item.id)}>
                              <Trash2 className="h-4 w-4" />
                              <span className="sr-only">Delete</span>
                            </Button>
                            {/* Add View button later if needed */}
                          </TableCell>
                        </TableRow>
                      ))
                    ) : (
                      <TableRow>
                        <TableCell colSpan={5} className="text-center text-muted-foreground">
                          No knowledge items found.
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>
        )}

        {activeView === 'upload' && (
          <div>
            <h1 className="text-3xl font-bold tracking-tight mb-6">Add to Knowledge Base</h1>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Section 1: Upload Files */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center"><FileUp className="mr-2 h-5 w-5" /> Upload Documents</CardTitle>
                  <CardDescription>
                    Upload relevant documents (PDF, DOCX, TXT) containing support information, product details, FAQs, etc.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                   {/* TODO: Add Drag-and-Drop Area */}
                   <div>
                     <label htmlFor="file-upload" className="sr-only">Choose files</label>
                     <Input
                       id="file-upload"
                       type="file"
                       multiple
                       onChange={handleFileChange}
                       className="cursor-pointer"
                     />
                   </div>
                   {/* Display selected files (optional) */}
                   {selectedFiles.length > 0 && (
                     <div className="text-sm text-muted-foreground space-y-1">
                       <p className="font-medium">Selected:</p>
                       <ul>
                         {selectedFiles.map((file, index) => (
                           <li key={index}>{file.name}</li>
                         ))}
                       </ul>
                     </div>
                   )}
                   <Button onClick={handleUploadFiles} disabled={selectedFiles.length === 0}>
                     Upload Selected Files
                   </Button>
                   {/* TODO: Add Progress Indicators */}
                </CardContent>
              </Card>

              {/* Section 2: Paste Text */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center"><ClipboardPaste className="mr-2 h-5 w-5" /> Paste Text Content</CardTitle>
                  <CardDescription>
                    Paste text directly (e.g., from websites, emails). Give it a descriptive title.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <label htmlFor="content-title" className="block text-sm font-medium mb-1">Content Title <span className="text-red-500">*</span></label>
                    <Input
                      id="content-title"
                      value={pastedTitle}
                      onChange={(e) => setPastedTitle(e.target.value)}
                      placeholder="e.g., Website - Return Policy"
                      required
                    />
                  </div>
                  <div>
                    <label htmlFor="pasted-content" className="block text-sm font-medium mb-1">Pasted Text <span className="text-red-500">*</span></label>
                    <Textarea
                      id="pasted-content"
                      value={pastedContent}
                      onChange={(e) => setPastedContent(e.target.value)}
                      placeholder="Paste your content here..."
                      rows={8} // Adjust as needed
                      required
                    />
                  </div>
                  <Button onClick={handleSavePastedText} disabled={!pastedTitle || !pastedContent}>
                    Save Pasted Text
                  </Button>
                  {/* TODO: Add Feedback Messages */}
                </CardContent>
              </Card>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
