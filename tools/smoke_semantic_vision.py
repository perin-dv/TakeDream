"""Opt-in real inference/cache smoke; never runs as part of unit tests."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.project_manager import ProjectManager
from core.storage import write_json
from core.visual_semantics import VisualSemanticsPipeline
from media.ffmpeg_tools import FFmpegTools


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--duration-ms",type=int,help="Known source duration; otherwise probe the source")
    args = parser.parse_args()
    source=args.source.resolve()
    manager=ProjectManager(args.output.resolve()/"projects")
    project=manager.create_project("Real semantic smoke",source,"Casamento","Highlight")
    tools=FFmpegTools()
    if args.duration_ms:
        duration=args.duration_ms
    else:
        metadata=tools.probe(source)
        duration=int(float(metadata["container"]["duration_seconds"])*1000)
    candidate=dict(asset_id="smoke",scene_id=0,path=str(source),start_ms=0,end_ms=duration,duration_ms=duration,score=70)
    pipeline=VisualSemanticsPipeline(manager,tools)
    first=pipeline.run(project,[candidate],stage=lambda text:print(text,flush=True))
    second=pipeline.run(project,[candidate],stage=lambda text:print(text,flush=True))
    shot=first["analysis"]["shots"][0]
    assert len(shot["embedding"])==512
    assert second["analysis"]["reused_from_cache"]==1
    write_json(args.output/"smoke-result.json",{"model":first["analysis"]["model"],
        "resolved_revision":shot.get("resolved_revision"),"embedding_dimensions":len(shot["embedding"]),
        "top_tags":shot["tags"][:8],"roles":shot["roles"],"cache_reused":True,"project":str(project)})
    print("Real CPU inference and cache verified",flush=True)


if __name__=="__main__":
    main()
