#!/usr/bin/env python3
"""Recompute global 3D coordinates for all document chunks."""
import logging
import os
from contextlib import contextmanager
from typing import List, Tuple

import numpy as np
from sklearn.preprocessing import StandardScaler
import umap
from google.cloud.sql.connector import Connector

# Environment variables
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
INSTANCE_CONNECTION_NAME = os.environ["CLOUD_SQL_INSTANCE"]
DB_USER = os.environ["CLOUD_SQL_USER"]
DB_PASS = os.environ["CLOUD_SQL_PASSWORD"]
DB_NAME = os.environ.get("CLOUD_SQL_DB", "docs")

connector = Connector()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
logger = logging.getLogger("mapper")

@contextmanager
def get_conn():
    conn = connector.connect(
        INSTANCE_CONNECTION_NAME,
        "pg8000",
        user=DB_USER,
        password=DB_PASS,
        db=DB_NAME,
        ip_type="PRIVATE",
    )
    try:
        yield conn
    finally:
        conn.close()

def fetch_embeddings() -> Tuple[List[int], List[List[float]]]:
    """Fetch all chunk embeddings from the database."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, embedding::text FROM chunks ORDER BY id")
        rows = cur.fetchall()
        cur.close()

    ids: List[int] = []
    embeddings: List[List[float]] = []
    for chunk_id, emb_text in rows:
        ids.append(int(chunk_id))
        if isinstance(emb_text, str):
            emb = [float(x) for x in emb_text.strip("[]").split(",")]
        else:
            emb = list(emb_text)
        embeddings.append(emb)
    return ids, embeddings

def reduce_to_3d(embeddings: List[List[float]]) -> List[Tuple[float, float, float]]:
    logger.info("Reducing %d embeddings to 3D...", len(embeddings))
    arr = np.array(embeddings)
    scaler = StandardScaler()
    arr = scaler.fit_transform(arr)
    n = len(embeddings)
    if n < 10:
        from sklearn.decomposition import PCA
        reducer = PCA(n_components=min(3, n), random_state=42)
    else:
        n_neighbors = min(15, max(2, n - 1))
        reducer = umap.UMAP(
            n_components=3,
            n_neighbors=n_neighbors,
            min_dist=0.1,
            metric="cosine",
            random_state=42,
        )
    coords = reducer.fit_transform(arr)
    if coords.shape[1] < 3:
        coords = np.hstack([coords, np.zeros((coords.shape[0], 3 - coords.shape[1]))])
    max_val = np.max(np.abs(coords))
    if max_val > 0:
        coords = coords * 10 / max_val
    return [(float(x), float(y), float(z)) for x, y, z in coords]

def store_coords(chunk_ids: List[int], coords: List[Tuple[float, float, float]]) -> None:
    logger.info("Storing %d 3D coordinates...", len(chunk_ids))
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM chunks_3d")
        cur.executemany(
            """
            INSERT INTO chunks_3d (chunk_id, x, y, z)
            VALUES (%s, %s, %s, %s)
            """,
            [
                (cid, x, y, z)
                for cid, (x, y, z) in zip(chunk_ids, coords)
            ],
        )
        conn.commit()
        cur.close()
    logger.info("3D coordinates updated.")

def main() -> None:
    ids, embeddings = fetch_embeddings()
    if not ids:
        logger.warning("No embeddings found. Nothing to map.")
        return
    coords = reduce_to_3d(embeddings)
    store_coords(ids, coords)

if __name__ == "__main__":
    main()
