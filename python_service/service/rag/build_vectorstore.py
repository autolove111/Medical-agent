import logging

from service.rag.embedding import build_global_vectorstore, create_embeddings


logger = logging.getLogger("knowledge.build_vectorstore")
logging.basicConfig(level=logging.INFO)


def main():
    print("Start building global vectorstore with local embedding model")

    try:
        embeddings = create_embeddings(purpose="rag")
        build_global_vectorstore(embeddings)
        print("Global vectorstore build complete")
    except Exception as exc:
        logger.exception("Global vectorstore build failed: %s", exc)


if __name__ == "__main__":
    main()
