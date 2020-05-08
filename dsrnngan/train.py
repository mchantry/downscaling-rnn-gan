import gc
import os

import netCDF4
import numpy as np
import tensorflow as tf
tf.compat.v1.disable_eager_execution()

import gan
import data
import models
import noise
import plots


path = os.path.dirname(os.path.abspath(__file__))


def setup_gan(data_file=None, application="mchrzc",
    num_epochs=1, steps_per_epoch=None, training_ratio=1,
    batch_size=32, sample_random=False,
    validation_frac=0.1, validation_seed=1234,
    scaling_fn=path+"/../data/scale_rzc.npy",
    n_samples=None, random_seed=None, lr_disc=0.0001, lr_gen=0.0001):

    (gen, _) = models.generator()
    init_model = models.initial_state_model()
    (gen_init, noise_shapes) = models.generator_initialized(
        gen, init_model)
    disc = models.discriminator()
    wgan = gan.WGANGP(gen_init, disc, lr_disc=lr_disc, lr_gen=lr_gen)

    with netCDF4.Dataset(data_file, 'r') as ds:
        ds.set_auto_maskandscale(False)
        if n_samples is None:
            seq = np.array(ds["sequences"][:], copy=False)
        else:
            if sample_random:
                prng = np.random.RandomState(seed=random_seed)
                ind = prng.choice(ds["sequences"].shape[0], n_samples,
                    replace=False)
                seq = np.array(ds["sequences"][ind,...], copy=False)
            else:
                seq = np.array(ds["sequences"][n_samples[0]:n_samples[1]],
                    copy=False)

    prng = np.random.RandomState(seed=validation_seed)
    N_seq = seq.shape[0]
    N_validation = int(round(N_seq*validation_frac))
    ind_valid = prng.choice(N_seq, N_validation, replace=False)
    validation = np.zeros(N_seq, dtype=bool)
    validation[ind_valid] = True
    training = ~validation

    if application == "mchrzc":
        dec = data.RainRateDecoder(scaling_fn, below_val=np.log10(0.025))
        zeros_frac = 0.2
    elif application == "goescod":
        dec = data.CODDecoder(below_val=0.0)
        zeros_frac = 0.0
    else:
        raise ValueError("Unknown application.")

    downsampler = data.LogDownsampler(min_val=dec.below_val,
        threshold_val=dec.value_range[0])
    batch_gen_train = data.BatchGenerator(seq[training,...],
        dec, downsampler, batch_size=batch_size, random_seed=random_seed,
        zeros_frac=zeros_frac)
    batch_gen_valid = data.BatchGenerator(seq[validation,...],
        dec, downsampler, batch_size=batch_size, random_seed=random_seed,
        zeros_frac=zeros_frac)

    if steps_per_epoch is None:
        steps_per_epoch = batch_gen_train.N//batch_gen_train.batch_size

    gc.collect()

    return (wgan, batch_gen_train, batch_gen_valid,
        noise_shapes, steps_per_epoch)


def train_gan(wgan, batch_gen_train, batch_gen_valid, noise_shapes,
    steps_per_epoch, num_epochs,
    plot_samples=8, plot_fn="../figures/progress.pdf"):
    
    img_shape = batch_gen_train.img_shape
    noise_gen = noise.NoiseGenerator(noise_shapes(img_shape),
        batch_size=batch_gen_train.batch_size)

    for epoch in range(num_epochs):
        print("Epoch {}/{}".format(epoch+1,num_epochs))
        loss_log = wgan.train(batch_gen_train, noise_gen,
            steps_per_epoch, training_ratio=5)
        plots.plot_sequences(wgan.gen, batch_gen_valid, noise_gen, 
            num_samples=plot_samples, out_fn=plot_fn)

    return loss_log