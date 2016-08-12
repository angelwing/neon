# ----------------------------------------------------------------------------
# Copyright 2016 Nervana Systems Inc.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ----------------------------------------------------------------------------
import numpy as np
import os
from tqdm import tqdm
from neon.data import load_cifar10
from neon.data.dataloader_transformers import OneHot, TypeCast, BGRMeanSubtract
from neon.util.persist import ensure_dirs_exist
from aeon import DataLoader
from PIL import Image


def ingest_cifar10(padded_size, overwrite=False):
    '''
    Save CIFAR-10 dataset as PNG files
    '''
    out_dir = os.path.join(os.environ['CIFAR_DATA_PATH'], 'cifar-extracted')
    dataset = dict()
    dataset['train'], dataset['val'], _ = load_cifar10(out_dir, normalize=False)
    pad_size = (padded_size - 32) // 2 if padded_size > 32 else 0
    pad_width = ((0, 0), (pad_size, pad_size), (pad_size, pad_size))

    set_names = ('train', 'val')
    manifest_files = [os.path.join(out_dir, setn + '-index.csv') for setn in set_names]

    if (all([os.path.exists(manifest) for manifest in manifest_files]) and not overwrite):
        return

    # Write out label files and setup directory structure
    lbl_paths, img_paths = dict(), dict(train=dict(), val=dict())
    for lbl in range(10):
        lbl_paths[lbl] = ensure_dirs_exist(os.path.join(out_dir, 'labels', str(lbl) + '.txt'))
        np.savetxt(lbl_paths[lbl], [lbl], fmt='%d')
        for setn in ('train', 'val'):
            img_paths[setn][lbl] = ensure_dirs_exist(os.path.join(out_dir, setn, str(lbl) + '/'))

    # Now write out image files and manifests
    for setn, manifest in zip(set_names, manifest_files):
        records = []
        for idx, (img, lbl) in tqdm(enumerate(zip(*dataset[setn]))):
            img_path = os.path.join(img_paths[setn][lbl[0]], str(idx) + '.png')
            im = np.pad(img.reshape((3, 32, 32)), pad_width, mode='mean')
            im = Image.fromarray(np.uint8(np.transpose(im, axes=[1, 2, 0]).copy()))
            im.save(img_path, format='PNG')
            records.append((img_path, lbl_paths[lbl[0]]))
        np.savetxt(manifest, records, fmt='%s,%s')


def get_ingest_file(filename):
    '''
    prepends the environment variable data path after checking that it has been set
    '''
    if os.environ.get('CIFAR_DATA_PATH') is None:
        raise RuntimeError("Missing required env variable CIFAR_DATA_PATH")

    return os.path.join(os.environ['CIFAR_DATA_PATH'], 'cifar-extracted', filename)


def common_config(set_name, batch_size, subset_pct):
    manifest_file = get_ingest_file(set_name + '-index.csv')
    cache_root = ensure_dirs_exist(os.path.join(os.environ['CIFAR_DATA_PATH'], 'cifar-cache/'))

    return {
               'manifest_filename': manifest_file,
               'minibatch_size': batch_size,
               'subset_fraction': float(subset_pct/100.0),
               'macrobatch_size': 5000,
               'type': 'image,label',
               'cache_directory': cache_root,
               'image': {'height': 32,
                         'width': 32,
                         'scale': [0.8, 0.8]},
               'label': {'binary': False}
            }


def wrap_dataloader(dl):
    dl = OneHot(dl, index=1, nclasses=10)
    dl = TypeCast(dl, index=0, dtype=np.float32)
    dl = BGRMeanSubtract(dl, index=0)
    return dl


def make_train_loader(backend_obj, subset_pct=100, random_seed=0):
    aeon_config = common_config('train', backend_obj.bsz, subset_pct)
    aeon_config['shuffle_manifest'] = True
    aeon_config['shuffle_every_epoch'] = True
    aeon_config['random_seed'] = random_seed
    aeon_config['image']['center'] = False
    aeon_config['image']['flip_enable'] = True

    return wrap_dataloader(DataLoader(aeon_config, backend_obj))


def make_validation_loader(backend_obj, subset_pct=100):
    aeon_config = common_config('val', backend_obj.bsz, subset_pct)
    return wrap_dataloader(DataLoader(aeon_config, backend_obj))


def make_tuning_loader(backend_obj):
    aeon_config = common_config('train', backend_obj.bsz, subset_pct=20)
    aeon_config['shuffle_manifest'] = True
    aeon_config['shuffle_every_epoch'] = True
    return wrap_dataloader(DataLoader(aeon_config, backend_obj))
