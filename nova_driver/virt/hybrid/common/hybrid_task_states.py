"""Possible task states for instances. extended for hybrid driver

Compute instance task states represent what is happening to the instance at the
current moment.
"""

# TASK STATES FOR INSTANCE SPAWING

DOWNLOADING = 'downloading'       # downloading image file from glance
CONVERTING = 'converting'         # convert source format to provider one
PACKING = 'packing'               # making provider package
NETWORK_CREATING = 'network_creating'
IMPORTING = 'importing'           # importing image to the provider
VM_CREATING = 'vm_creating'       # create and power on VM

# TASK STATES FOR INSATCNE MIGRATION
EXPORTING = 'exporting'
UPLOADING = 'uploading'
PROVIDER_PREPARING = 'provider_preparing'
