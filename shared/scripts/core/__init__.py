"""Reusable, domain-agnostic runtime engine for graph plugins.

Pure stdlib. Knows nothing about any specific graph, node, agent or field set — graphs pass
their own configuration in. Imported as ``from core.<module> import ...`` with
``$CLAUDE_PLUGIN_ROOT/shared/scripts`` on sys.path.
"""
