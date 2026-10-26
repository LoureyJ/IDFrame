"""Export a visually selected checkpoint without repeating training."""

import argparse
from pathlib import Path

import torch

from adapt_modnet import MODNet, export_onnx


def main():
    """Load a selected CPU checkpoint and export its matte output to an ONNX file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    torch.set_num_threads(4)
    model = MODNet(backbone_pretrained=False)
    state = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    model.load_state_dict(
        {name.removeprefix("module."): value for name, value in state.items()}
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    export_onnx(model.eval(), args.output)


if __name__ == "__main__":
    main()
