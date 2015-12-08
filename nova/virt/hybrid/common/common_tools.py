import os
import shutil
import subprocess

from nova.openstack.common import log as logging

LOG = logging.getLogger(__name__)


def create_user_data_iso(iso_name, user_data, work_dir):
    iso_dir = "%s/iso" % work_dir
    full_iso_name = "%s/%s" % (work_dir, iso_name)
    os.makedirs(iso_dir)
    with open("%s/userdata.txt" % iso_dir, "w+") as f:
        for k, v in user_data.iteritems():
            f.write("%s=%s\n" % (k, v))
    subprocess.call(
        "genisoimage -o %s %s" % (full_iso_name, iso_dir), shell=True)
    shutil.rmtree(iso_dir, ignore_errors=True)
    return full_iso_name


def create_user_data_floppy(floppy_name, user_data, work_dir):
    floppy_dir = "%s/floppy" % work_dir
    full_floppy_name = "%s/%s" % (work_dir, floppy_name)
    subprocess.call(
        "sudo mkfs.msdos -C %s 1440" % full_floppy_name,
        shell=True)
    os.makedirs(floppy_dir)
    subprocess.call(
        "sudo mount -o loop,users,noatime,umask=0 %s %s" %
        (full_floppy_name, floppy_dir),
        shell=True)
    with open("%s/user_data.txt" % floppy_dir, "w+") as f:
        for k, v in user_data.iteritems():
            f.write("%s=%s\n" % (k, v))
    subprocess.call(
        "sudo umount %s" % floppy_dir, shell=True)
    shutil.rmtree(floppy_dir, ignore_errors=True)
    return full_floppy_name

def convert_vm(src_format, src_file, dst_format, dst_file):
    if src_format == dst_file:
        os.rename(src_file, dst_file)
    else:
        convert_command = ("qemu-img convert -f %s -O %s %s %s" % 
            (src_format, dst_format, src_file, dst_file))
    
        convert_result = subprocess.call([convert_command], shell=True)
    
        if convert_result != 0:
            LOG.error('convert %s to %s failed' % (src_format, dst_format))

