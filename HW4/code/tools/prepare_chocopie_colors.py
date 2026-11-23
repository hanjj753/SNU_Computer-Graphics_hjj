"""Create relative color-matched copies; never overwrite the photographed textures.

Offline dependency: Pillow (with LittleCMS) and NumPy. Rendering does not import this.
The front is a color reference, not a measured reflectance target. This process fits
one global linear RGB matrix per face, preserving pixel positions, labels and size.
"""
from pathlib import Path
from io import BytesIO
import argparse,hashlib,json
import numpy as np
from PIL import Image,ImageCms

FILES={'front':'chocopie_front.jpg','back':'chocopie_back.png',
       'right':'chocopie_bottom.png','left':'chocopie_top.png',
       'top':'chocopie_right.png','bottom':'chocopie_left.jpg'}
SRGB=ImageCms.createProfile('sRGB')

def decode(rgb):
    return np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)

def encode(rgb):
    rgb=np.clip(rgb,0.,1.)
    return np.where(rgb<=.0031308,12.92*rgb,1.055*rgb**(1/2.4)-.055)

def gamut_map(rgb):
    # Bring out-of-gamut colors toward neutral at the same luminance. Merely
    # clipping the red channel would flatten bright folds in the printed panel.
    y=np.clip(rgb@np.array([.2126,.7152,.0722]),0.,1.)[...,None]
    chroma=rgb-y
    positive=np.maximum(chroma.max(2,keepdims=True),1e-12)
    negative=np.maximum(-chroma.min(2,keepdims=True),1e-12)
    scale=np.minimum(1.,np.minimum((1-y)/positive,y/negative))
    return np.clip(y+scale*chroma,0.,1.)

def colorants(profile):
    return np.array([getattr(profile,name)[0] for name in
                     ('red_colorant','green_colorant','blue_colorant')]).T

def load(path):
    image=Image.open(path)
    embedded=image.info.get('icc_profile')
    if embedded:
        profile=ImageCms.ImageCmsProfile(BytesIO(embedded))
        description=ImageCms.getProfileName(profile).strip()
        # These phone PNGs use P3 primaries with an sRGB transfer curve.
        # Keep out-of-gamut values in floating point until the final correction.
        if not profile.profile.is_matrix_shaper or 'sRGB Transfer' not in description:
            raise ValueError(f'Unsupported input profile: {description}')
        primary=np.linalg.solve(colorants(SRGB),colorants(profile.profile))
    else:
        description='Untagged; treated as sRGB'
        primary=np.eye(3)
    pixels=np.array(image.convert('RGB'),dtype=np.float32)/255.
    return image,pixels,decode(pixels)@primary.T,primary,description

def anchors(rgb,linear):
    step=max(1,max(rgb.shape[:2])//768)
    a=rgb[::step,::step];b=linear[::step,::step]
    maximum=a.max(2);minimum=a.min(2)
    white=(minimum>.4)&((maximum-minimum)/np.maximum(maximum,1e-6)<.16)
    brightness=a.mean(2)
    if white.sum()<100:raise ValueError('Not enough neutral printed pixels')
    white&=brightness>=np.quantile(brightness[white],.65)
    red=(a[:,:,0]>.3)&(a[:,:,1]<a[:,:,0]*.33)&(a[:,:,2]<a[:,:,0]*.33)
    if red.sum()<100:raise ValueError('Not enough red printed pixels')
    return np.stack([np.median(b[white],axis=0),np.median(b[red],axis=0)],axis=1),white,red

def prepare(source_dir,output_dir,mode='matched'):
    source_dir=Path(source_dir).resolve();output_dir=Path(output_dir).resolve()
    if output_dir==source_dir:raise ValueError('Output must be a separate directory')
    output_dir.mkdir(parents=True,exist_ok=True)
    _,reference_rgb,reference_linear,_,_=load(source_dir/FILES['front'])
    reference,_,_=anchors(reference_rgb,reference_linear)
    manifest={'reference':FILES['front'],'reference_sha256':hashlib.sha256((source_dir/FILES['front']).read_bytes()).hexdigest(),
              'mode':mode,'color_space':'sRGB','scope':'Relative matching, not measured albedo recovery',
              'method':'Decode sRGB transfer, convert embedded P3 primaries to linear sRGB, fit white-print and red-ink anchors with one global RGB matrix, compress out-of-gamut chroma at fixed luminance, encode sRGB PNG',
              'reference_anchors_linear':reference.tolist(),'faces':{}}
    for face,name in FILES.items():
        if face=='front':continue
        image,rgb,linear,primary,profile=load(source_dir/name)
        observed,white,red=anchors(rgb,linear)
        # Minimum change from a diagonal white-balance transform, subject to
        # matching both shared ink colors. Black remains black (no added offset).
        diagonal=np.diag(reference[:,0]/observed[:,0])
        correction=diagonal+(reference-diagonal@observed)@np.linalg.pinv(observed)
        already_matched=np.max(np.abs(encode(observed)-encode(reference)))<=2/255
        if mode=='icc_only' or already_matched:correction=np.eye(3)
        corrected=linear@correction.T
        output=Image.fromarray(np.uint8(np.round(encode(gamut_map(corrected))*255)))
        target=output_dir/(Path(name).stem+'.png')
        assert target!=source_dir/name
        output.save(target,icc_profile=ImageCms.ImageCmsProfile(SRGB).tobytes())
        entry={'source':name,'source_sha256':hashlib.sha256((source_dir/name).read_bytes()).hexdigest(),
               'output':target.name,'size':list(image.size),'input_profile':profile,
               'primary_matrix_to_srgb':primary.tolist(),'matching_matrix_linear':correction.tolist(),
               'source_anchors_linear':observed.tolist(),'mapped_anchors_linear':(correction@observed).tolist(),
               'already_matched':bool(already_matched),
               'mean_rgb_before_for_renderer':np.mean(rgb**2.2,axis=(0,1)).tolist(),
               'mean_rgb_after_for_renderer':np.mean((np.asarray(output)/255.)**2.2,axis=(0,1)).tolist(),
               'fraction_pixels_gamut_compressed':float(np.any((corrected<0)|(corrected>1),axis=2).mean())}
        manifest['faces'][face]=entry
        print(face,'already matched' if already_matched else 'corrected',
              'mean',np.round(entry['mean_rgb_before_for_renderer'],3),'->',np.round(entry['mean_rgb_after_for_renderer'],3),flush=True)
    (output_dir/'color_match_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    project=Path(__file__).resolve().parents[1]
    parser.add_argument('--source',type=Path,default=project/'textures')
    parser.add_argument('--output',type=Path,default=project/'textures'/'color_matched')
    parser.add_argument('--mode',choices=('matched','icc_only'),default='matched')
    args=parser.parse_args();prepare(args.source,args.output,args.mode)
