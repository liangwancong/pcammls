from pcammls import * 
import cv2
import numpy
import sys
import os
import numpy as np
from ctypes import *

def select_device():
    ''' a simple way to get device like original sdk  '''
    argv = sys.argv
    sn = ''
    for idx in range(len(argv)):
        if argv[idx]=='-sn' and idx<len(argv)-1:
            sn = argv[idx+1]
            break
    dev_list = selectDevice(TY_INTERFACE_ALL,sn,'',10)
    print ('device found:')
    for idx in range(len(dev_list)):
        dev = dev_list[idx]
        print ('{} -- {} \t {}'.format(idx,dev.id,dev.iface.id))
    if  len(dev_list)==0:
        return None,None
    if len(dev_list) == 1 and sn!='':
        selected_idx = 0 
    else:
        selected_idx  = int(input('select a device:'))
    if selected_idx < 0 or selected_idx >= len(dev_list):
        return None,None
    dev = dev_list[selected_idx]
    return dev.iface.id, dev.id

def decode_rgb(pixelFormat,image):
    if pixelFormat == TY_PIXEL_FORMAT_YUYV:
        return cv2.cvtColor(image,cv2.COLOR_YUV2BGR_YUYV)
    if pixelFormat == TY_PIXEL_FORMAT_YVYU: 
        return cv2.cvtColor(image,cv2.COLOR_YUV2BGR_YVYU)
    if pixelFormat == TY_PIXEL_FORMAT_BAYER8GB:
        return cv2.cvtColor(image,cv2.COLOR_BayerGB2BGR)
    if pixelFormat == TY_PIXEL_FORMAT_JPEG:
        return cv2.imdecode(image, CV_LOAD_IMAGE_COLOR)
    return image

def fetch_frame_loop(handle):
    comps = TYGetComponentIDs(handle)
    TYEnableComponents(handle,TY_COMPONENT_DEPTH_CAM & comps)
    #TYEnableComponents(handle,TY_COMPONENT_RGB_CAM_LEFT & comps)
    #TYEnableComponents(handle,TY_COMPONENT_IR_CAM_LEFT)
    #TYEnableComponents(handle,TY_COMPONENT_IR_CAM_RIGHT)
    TYEnableComponents(handle,TY_COMPONENT_RGB_CAM & comps)
    TYSetEnum(handle,TY_COMPONENT_DEPTH_CAM,TY_ENUM_IMAGE_MODE,TY_IMAGE_MODE_DEPTH16_640x480)
    sz = TYGetFrameBufferSize(handle)
    print ('buffer size:{}'.format(sz))
    if sz<0:
        print ('error size')
        return 
    buffs=[char_ARRAY(sz),char_ARRAY(sz)]
    TYEnqueueBuffer(handle,buffs[0],sz)
    TYEnqueueBuffer(handle,buffs[1],sz)

    src_buffer = uint8_t_ARRAY(1280 * 960 * 3)
    dst_buffer = uint8_t_ARRAY(1280 * 960 * 3)

    src_depth_buffer = uint16_t_ARRAY(640 * 480)
    dst_depth_buffer = uint16_t_ARRAY(1280 * 960)

    depth_calib = TY_CAMERA_CALIB_INFO()
    color_calib = TY_CAMERA_CALIB_INFO()
    ret = TYGetStruct(handle, TY_COMPONENT_DEPTH_CAM, TY_STRUCT_CAM_CALIB_DATA, depth_calib, depth_calib.CSize());
    ret = TYGetStruct(handle, TY_COMPONENT_RGB_CAM, TY_STRUCT_CAM_CALIB_DATA, color_calib, color_calib.CSize());
    print("Depth cam calib data:")
    print("                 {} {}".format(depth_calib.intrinsicWidth, depth_calib.intrinsicHeight))
    print("                 {}".format(depth_calib.intrinsic.data))
    print("                 {}".format(depth_calib.extrinsic.data))
    print("                 {}".format(depth_calib.distortion.data))
 
    print('start cap')
    TYStartCapture(handle)
    img_index =0 
    while True:
        frame = TY_FRAME_DATA()
        try:
            TYFetchFrame(handle,frame.this,2000)
            images = frame.image
            for img in images:
                if not img.buffer:
                    continue
                arr = img.as_nparray()
                if img.componentID == TY_COMPONENT_DEPTH_CAM:
                     arr_depth = arr;
                if img.componentID == TY_COMPONENT_RGB_CAM:
                    arr_rgb = decode_rgb(img.pixelFormat,arr)
            
            sp = arr_rgb.shape
            src_rgb = TYInitImageData(sp[0] * sp[1] * 3, src_buffer, sp[1], sp[0])
            dst_rgb = TYInitImageData(sp[0] * sp[1] * 3, dst_buffer, sp[1], sp[0])
            src_rgb.pixelFormat = TY_PIXEL_FORMAT_RGB;
            dst_rgb.pixelFormat = TY_PIXEL_FORMAT_RGB;
            
            for i in range(0, sp[0], 1):
                for j in range(0, sp[1], 1):
                     src_buffer.__setitem__(3*i*sp[1] + 3*j + 0, int(arr_rgb[i, j, 0]))
                     src_buffer.__setitem__(3*i*sp[1] + 3*j + 1, int(arr_rgb[i, j, 1]))
                     src_buffer.__setitem__(3*i*sp[1] + 3*j + 2, int(arr_rgb[i, j, 2]))

            TYUndistortImage(color_calib, src_rgb, color_calib.intrinsic, dst_rgb)
            undistort_rgb = dst_rgb.as_nparray();
            cv2.imshow('undistort_rgb',undistort_rgb)

            sp = arr_depth.shape
            for i in range(0, sp[0], 1):
                for j in range(0, sp[1], 1):
                    src_depth_buffer.__setitem__(i*sp[1] + j, int(arr_depth[i, j]))
                     
            TYMapDepthImageToColorCoordinate(depth_calib, 640, 480, src_depth_buffer.cast(), color_calib, 1280, 960, dst_depth_buffer.cast())
            dst_depth16 = TYInitImageData(1280 * 960 * 2, dst_depth_buffer, 1280, 960)
            dst_depth16.pixelFormat = TY_PIXEL_FORMAT_DEPTH16;
            dst_depth16_arr = dst_depth16.as_nparray()
            dst_depthu8 =  cv2.convertScaleAbs(dst_depth16_arr, alpha=(255.0/4000.0))
            cv2.imshow('registration_depth',dst_depthu8)

            k = cv2.waitKey(10)
            if k==ord('q'): 
                break

            TYEnqueueBuffer(handle,frame.userBuffer,frame.bufferSize)
            print('{} cap ok'.format(img_index))
            img_index+=1
        except Exception as err:
            print (err)
    TYStopCapture(handle)
    print('done')

def main():
    TYInitLib()
    iface_id,dev_sn = select_device()
    if not dev_sn:
        print ('no device')
        return 
    iface_handle = TYOpenInterface(iface_id)
    dev_handle = TYOpenDevice(iface_handle,dev_sn)
    fetch_frame_loop(dev_handle)
    TYCloseDevice(dev_handle)
    TYCloseInterface(iface_handle)
    TYDeinitLib()
    pass



if __name__=='__main__':
    main()

