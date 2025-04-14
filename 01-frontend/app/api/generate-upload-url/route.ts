import { NextRequest, NextResponse } from 'next/server';
import { Storage } from '@google-cloud/storage';
import { v4 as uuidv4 } from 'uuid'; // For generating unique names

// Ensure these environment variables are set in your Cloud Run service
const BUCKET_NAME = process.env.GCS_BUCKET_NAME;
// GCP_PROJECT should be implicitly available in Cloud Run environment
// GOOGLE_APPLICATION_CREDENTIALS is usually not needed if using default service account

if (!BUCKET_NAME) {
  throw new Error("Missing GCS_BUCKET_NAME environment variable");
}

const storage = new Storage(); // Assumes credentials are automatically available in the Cloud Run env
const bucket = storage.bucket(BUCKET_NAME);

export async function POST(request: NextRequest) {
  try {
    // Destructure originalTitle as well
    const { filename, contentType, originalTitle } = await request.json();

    if (!filename || !contentType) {
      return NextResponse.json({ error: 'Missing filename or contentType' }, { status: 400 });
    }

    // --- Security: Sanitize and create a unique object name ---
    // Sanitize the filename received from the frontend
    const safeFilename = filename.replace(/[^a-zA-Z0-9._-]/g, '_');
    // Create a unique path/name
    const uniqueObjectName = `uploads/${uuidv4()}-${safeFilename}`;
    // ---------------------------------------------------------

    const file = bucket.file(uniqueObjectName);

    // --- Define the custom header ---
    // Use the originalTitle for the metadata value if provided (for text), otherwise use filename
    // This ensures the backend gets the user's intended title via metadata
    const metadataValue = originalTitle || filename;
    const customMetadataHeader = {
        'x-goog-meta-originalfilename': metadataValue
    };
    // ------------------------------

    const options = {
      version: 'v4' as const,
      action: 'write' as const,
      expires: Date.now() + 15 * 60 * 1000, // 15 minutes
      contentType: contentType,
      // --- Explicitly include custom header in signature ---
      extensionHeaders: customMetadataHeader
      // ----------------------------------------------------
    };

    // Generate the signed URL
    const [signedUrl] = await file.getSignedUrl(options);

    // The GCS URI needed by your backend processing endpoint
    const gcsUri = `gs://${BUCKET_NAME}/${uniqueObjectName}`;

    console.log(`Generated signed URL for ${uniqueObjectName} (expires in 15 min), expects header x-goog-meta-originalfilename=${metadataValue}.`);

    // Return the necessary info, including the exact header(s) used for signing
    return NextResponse.json({
        signedUrl,
        gcsUri,
        objectName: uniqueObjectName,
        // Send back the exact header key/value pair used for signing
        metadataHeaders: customMetadataHeader
     });

  } catch (error) {
    console.error('Error generating signed URL:', error);
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: 'Failed to generate upload URL', details: errorMessage }, { status: 500 });
  }
}