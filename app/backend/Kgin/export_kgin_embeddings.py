#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch


def main() -> None:
    ap = argparse.ArgumentParser(description='Export KGIN item embeddings to NeoRAGRec format')
    ap.add_argument('--repo-root', required=True, help='Path to KGIN repo root')
    ap.add_argument('--data-path', required=True, help='Parent dir containing dataset folder, e.g. D:/kgin_data/')
    ap.add_argument('--dataset', required=True, help='Dataset folder name under data-path')
    ap.add_argument('--checkpoint', required=True, help='Path to saved model ckpt, e.g. weights/model_mydata.ckpt')
    ap.add_argument('--item-map', required=True, help='Path to item_id_map.json produced by export_for_kgat_kgin.py')
    ap.add_argument('--output-dir', required=True, help='Where to save kgin_movie_embeddings.npy and kgin_movie_id_map.json')
    ap.add_argument('--dim', type=int, default=64)
    ap.add_argument('--context-hops', type=int, default=3)
    ap.add_argument('--node-dropout-rate', type=float, default=0.5)
    ap.add_argument('--mess-dropout-rate', type=float, default=0.1)
    ap.add_argument('--sim-regularity', type=float, default=1e-4)
    ap.add_argument('--gpu-id', type=int, default=0)
    ap.add_argument('--cpu', action='store_true')
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    sys.path.insert(0, str(repo_root))

    from utils.data_loader import load_data
    from modules.KGIN import Recommender

    device = torch.device('cpu' if args.cpu or not torch.cuda.is_available() else f'cuda:{args.gpu_id}')

    model_args = SimpleNamespace(
        dataset=args.dataset,
        data_path=str(Path(args.data_path).resolve()) + '/',
        dim=args.dim,
        l2=1e-5,
        lr=1e-4,
        sim_regularity=args.sim_regularity,
        inverse_r=True,
        node_dropout=False,
        node_dropout_rate=args.node_dropout_rate,
        mess_dropout=False,
        mess_dropout_rate=args.mess_dropout_rate,
        batch_test_flag=True,
        channel=args.dim,
        cuda=(device.type == 'cuda'),
        gpu_id=args.gpu_id,
        Ks='[20, 40, 60, 80, 100]',
        test_flag='part',
        n_factors=4,
        ind='distance',
        context_hops=args.context_hops,
        batch_size=1024,
        test_batch_size=1024,
        save=False,
        out_dir='./weights/',
        epoch=1,
    )

    train_cf, test_cf, user_dict, n_params, graph, mat_list = load_data(model_args)
    _, _, mean_mat_list = mat_list

    model = Recommender(n_params, model_args, graph, mean_mat_list[0]).to(device)
    state = torch.load(args.checkpoint, map_location=device)
    model.load_state_dict(state)
    model.eval()

    with torch.no_grad():
        entity_gcn_emb, user_gcn_emb = model.generate()
        item_emb = entity_gcn_emb[:n_params['n_items']].detach().cpu().numpy().astype('float32')

    item_ids = json.loads(Path(args.item_map).read_text(encoding='utf-8'))
    if len(item_ids) != item_emb.shape[0]:
        raise ValueError(f'item map length {len(item_ids)} != item_emb rows {item_emb.shape[0]}')

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    np.save(out_dir / 'kgin_movie_embeddings.npy', item_emb)
    (out_dir / 'kgin_movie_id_map.json').write_text(json.dumps(item_ids, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f'[OK] Saved: {out_dir / "kgin_movie_embeddings.npy"}')
    print(f'[OK] Saved: {out_dir / "kgin_movie_id_map.json"}')
    print(f'[Info] shape={item_emb.shape}')


if __name__ == '__main__':
    main()
