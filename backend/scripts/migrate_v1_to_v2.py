import os
import sqlite3
import sys
import django
import json
import numpy as np
from pathlib import Path

# Setup Django
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

from django.db import transaction
from apps.content.models import ScopeItem, ContentItem, Post, Sentence
from apps.graph.models import ExistingLink
from apps.suggestions.models import Suggestion


def migrate_db(cursor):
    """Migrate SQLite tables to PostgreSQL via Django ORM."""

    # 1. Migrate ScopeItems
    print("Migrating ScopeItems...")
    cursor.execute("SELECT * FROM scope_items")
    scopes = cursor.fetchall()
    for s in scopes:
        ScopeItem.objects.get_or_create(
            scope_id=s["scope_id"],
            scope_type=s["scope_type"],
            defaults={
                "title": s["title"],
                "is_enabled": bool(s["is_enabled"]),
                "display_order": s.get("display_order", 0),
            },
        )
    print(f"Done. {len(scopes)} scopes processed.")

    # 2. Migrate ContentItems
    print("Migrating ContentItems...")
    cursor.execute("SELECT * FROM content_items")
    items = cursor.fetchall()
    for item in items:
        try:
            scope = ScopeItem.objects.get(
                scope_id=item["scope_id"], scope_type=item["scope_type"]
            )

            # xf_update_id was used for resources in V1 as the primary identifier for edits
            # V2 has explicit fields for both
            xf_post_id = item["xf_post_id"]
            xf_update_id = item.get("xf_update_id")

            # If it's a resource and we have update_id but no post_id,
            # we treat update_id as the primary body anchor for V2 consistency
            if item["content_type"] == "resource" and xf_update_id and not xf_post_id:
                xf_post_id = xf_update_id

            ci, created = ContentItem.objects.get_or_create(
                content_id=item["content_id"],
                content_type=item["content_type"],
                defaults={
                    "scope": scope,
                    "title": item["title"],
                    "url": item["url"],
                    "xf_post_id": xf_post_id,
                    "xf_update_id": xf_update_id,
                    "reply_count": item["reply_count"],
                    "view_count": item["view_count"],
                    "download_count": item["download_count"],
                    "pagerank_score": item["pagerank_score"] or 0.0,
                    "velocity_score": item["velocity_score"] or 0.0,
                    "distilled_text": item["distilled_text"] or "",
                    "content_hash": item["content_hash"] or "",
                    "is_deleted": bool(item.get("is_deleted", 0)),
                },
            )
        except ScopeItem.DoesNotExist:
            print(
                f"Warning: Scope {item['scope_id']} not found for item {item['content_id']}"
            )
            continue

    print(f"Done. {len(items)} items processed.")

    # 3. Migrate Posts
    print("Migrating Posts...")
    cursor.execute("SELECT * FROM posts")
    v1_posts = cursor.fetchall()
    for p in v1_posts:
        try:
            content_item = ContentItem.objects.get(
                content_id=p["content_id"], content_type=p["content_type"]
            )

            xf_post_id = p["xf_post_id"]
            xf_update_id = p.get("xf_update_id")
            if p["content_type"] == "resource" and xf_update_id and not xf_post_id:
                xf_post_id = xf_update_id

            Post.objects.get_or_create(
                content_item=content_item,
                defaults={
                    "xf_post_id": xf_post_id,
                    "xf_update_id": xf_update_id,
                    "raw_bbcode": p["raw_bbcode"],
                    "clean_text": p["clean_text"],
                    "char_count": p["char_count"],
                    "word_count": len(p["clean_text"].split())
                    if p["clean_text"]
                    else 0,
                },
            )
        except ContentItem.DoesNotExist:
            continue
    print(f"Done. {len(v1_posts)} posts processed.")

    # 4. Migrate Sentences
    print("Migrating Sentences...")
    cursor.execute("SELECT * FROM sentences")
    v1_sentences = cursor.fetchall()
    for s in v1_sentences:
        try:
            content_item = ContentItem.objects.get(
                content_id=s["content_id"], content_type=s["content_type"]
            )
            post = Post.objects.get(content_item=content_item)
            Sentence.objects.get_or_create(
                post=post,
                position=s["position"],
                defaults={
                    "content_item": content_item,
                    "text": s["text"],
                    "char_count": s["char_count"],
                    "start_char": s["start_char"],
                    "end_char": s["end_char"],
                    # word_position wasn't in V1 sentences, we can approximate or let re-sync fix it
                    "word_position": len(post.clean_text[: s["start_char"]].split()),
                },
            )
        except (ContentItem.DoesNotExist, Post.DoesNotExist):
            continue
    print(f"Done. {len(v1_sentences)} sentences processed.")

    # 5. Migrate ExistingLinks
    print("Migrating ExistingLinks...")
    cursor.execute("SELECT * FROM existing_links")
    v1_links = cursor.fetchall()
    for l in v1_links:
        try:
            from_item = ContentItem.objects.get(
                content_id=l["from_content_id"], content_type=l["from_content_type"]
            )
            to_item = ContentItem.objects.get(
                content_id=l["to_content_id"], content_type=l["to_content_type"]
            )
            ExistingLink.objects.get_or_create(
                from_content_item=from_item,
                to_content_item=to_item,
                anchor_text=l["anchor_text"] or "",
            )
        except ContentItem.DoesNotExist:
            continue
    print(f"Done. {len(v1_links)} links processed.")

    # 6. Migrate Suggestions
    print("Migrating Suggestions...")
    cursor.execute("SELECT * FROM suggestions")
    v1_sugs = cursor.fetchall()
    for s in v1_sugs:
        try:
            dest = ContentItem.objects.get(
                content_id=s["destination_content_id"],
                content_type=s["destination_content_type"],
            )
            host = ContentItem.objects.get(
                content_id=s["host_content_id"], content_type=s["host_content_type"]
            )

            cursor.execute(
                "SELECT position FROM sentences WHERE local_sentence_id = ?",
                (s["host_sentence_id"],),
            )
            sent_row = cursor.fetchone()
            if not sent_row:
                continue

            pos = sent_row["position"]
            host_sent = Sentence.objects.get(post__content_item=host, position=pos)

            Suggestion.objects.get_or_create(
                destination=dest,
                host=host,
                host_sentence=host_sent,
                defaults={
                    "anchor_phrase": s["anchor_phrase"],
                    "anchor_start": s["anchor_start"],
                    "anchor_end": s["anchor_end"],
                    "score_semantic": s["score_semantic"],
                    "score_keyword": s["score_keyword"],
                    "score_node_affinity": s["score_node_affinity"],
                    "score_quality": s["score_quality"],
                    "score_final": s["score_final"],
                    "status": s["status"],
                    "rejection_reason": s["rejection_reason"] or "",
                    "reviewer_note": s["reviewer_note"] or "",
                },
            )
        except (ContentItem.DoesNotExist, Sentence.DoesNotExist):
            continue
    print(f"Done. {len(v1_sugs)} suggestions processed.")


def migrate_embeddings(data_dir: Path):
    """Load V1 .npy embeddings and inject into pgvector columns."""
    metadata_path = data_dir / "embedding_artifacts.json"
    if not metadata_path.exists():
        print("Embedding metadata not found. Skipping vector migration.")
        return

    print("Migrating embeddings to pgvector...")
    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    # 1. Destination Embeddings
    dest_path = data_dir / "dest_embeddings.npy"
    if dest_path.exists():
        print("Loading destination embeddings...")
        dest_matrix = np.load(dest_path)
        content_keys = metadata.get("content_id_list", [])

        for idx, (c_id, c_type) in enumerate(content_keys):
            try:
                item = ContentItem.objects.get(content_id=c_id, content_type=c_type)
                item.embedding = dest_matrix[idx].tolist()
                item.save(update_fields=["embedding"])
            except ContentItem.DoesNotExist:
                continue
        print(f"Migrated {len(content_keys)} destination vectors.")

    # 2. Sentence Embeddings
    sent_path = data_dir / "sentence_embeddings.npy"
    sent_map_path = data_dir / "sentence_id_map.npy"
    if sent_path.exists() and sent_map_path.exists():
        print("Loading sentence embeddings...")
        sent_matrix = np.load(sent_path)
        sent_id_map = np.load(sent_map_path)

        for idx, v1_sent_id in enumerate(sent_id_map):
            # We need to map v1_sent_id back to something in V2.
            # V2 Sentences are unique by (post, position).
            # This requires a second pass or more SQLite lookups.
            # For simplicity in this script, we'll skip sentence embeddings
            # and recommend re-generating as they depend on exact spaCy version/splitting.
            pass
        print(
            "Sentence vector migration skipped (recommended to re-generate in V2 for consistency)."
        )


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate V1 SQLite data to V2 PostgreSQL."
    )
    parser.add_argument("db_path", help="Path to V1 linker.db")
    parser.add_argument(
        "--data-dir", help="Path to V1 data directory (for embeddings)", default=None
    )
    args = parser.parse_args()

    v1_db_path = args.db_path
    v1_data_dir = Path(args.data_dir) if args.data_dir else None

    if not os.path.exists(v1_db_path):
        print(f"Error: V1 DB not found at {v1_db_path}")
        return

    conn = sqlite3.connect(v1_db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        with transaction.atomic():
            migrate_db(cursor)

        if v1_data_dir:
            migrate_embeddings(v1_data_dir)

        print("\nMigration completed successfully!")
    except Exception as e:
        print(f"\nMigration failed: {e}")
        import traceback

        traceback.print_exc()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
