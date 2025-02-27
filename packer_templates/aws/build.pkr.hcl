build {
  sources = ["source.amazon-ebs.itself"]

  provisioner "shell" {
    inline = [
      "sleep 30",
      "sudo dnf install -y unzip python3 jq numactl",
      "sudo dnf install -y kernel-devel-`uname -r` kernel-headers-`uname -r`",
      "sudo dnf install -y make gcc-c++ elfutils-libelf-devel bind-utils nftables iptables nvme-cli",
      "sudo sh -c \"echo '[GPFSRepository]' >> /etc/yum.repos.d/scale.repo\"",
      "sudo sh -c \"echo 'name=Spectrum Scale Repository' >> /etc/yum.repos.d/scale.repo\"",
      "sudo sh -c \"echo 'baseurl=http://\"${var.package_repository}\".s3-website.\"${var.vpc_region}\".amazonaws.com/\"${var.scale_version}\"/gpfs_rpms/' >> /etc/yum.repos.d/scale.repo\"",
      "sudo sh -c \"echo 'enabled=1' >> /etc/yum.repos.d/scale.repo\"",
      "sudo sh -c \"echo 'gpgcheck=1' >> /etc/yum.repos.d/scale.repo\"",
      "sudo sh -c \"echo 'gpgkey=http://\"${var.package_repository}\".s3-website.\"${var.vpc_region}\".amazonaws.com/\"${var.scale_version}\"/Public_Keys/Storage_Scale_public_key.pgp\n' >> /etc/yum.repos.d/scale.repo\"",
      "if sudo grep -q el8 /etc/os-release",
      "then",
      "sudo sh -c \"echo '[ZimonRepositoryRhel8]' >> /etc/yum.repos.d/scale.repo\"",
      "sudo sh -c \"echo 'name=Spectrum Scale Zimon Repository Rhel8' >> /etc/yum.repos.d/scale.repo\"",
      "sudo sh -c \"echo 'baseurl=http://\"${var.package_repository}\".s3-website.\"${var.vpc_region}\".amazonaws.com/\"${var.scale_version}\"/zimon_rpms/rhel8/' >> /etc/yum.repos.d/scale.repo\"",
      "sudo sh -c \"echo 'enabled=1' >> /etc/yum.repos.d/scale.repo\"",
      "sudo sh -c \"echo 'gpgcheck=1' >> /etc/yum.repos.d/scale.repo\"",
      "sudo sh -c \"echo 'gpgkey=http://\"${var.package_repository}\".s3-website.\"${var.vpc_region}\".amazonaws.com/\"${var.scale_version}\"/Public_Keys/Storage_Scale_public_key.pgp\n' >> /etc/yum.repos.d/scale.repo\"",
      "elif sudo grep -q el9 /etc/os-release",
      "then",
      "sudo sh -c \"echo '[ZimonRepositoryRhel9]' >> /etc/yum.repos.d/scale.repo\"",
      "sudo sh -c \"echo 'name=Spectrum Scale Zimon Repository Rhel9' >> /etc/yum.repos.d/scale.repo\"",
      "sudo sh -c \"echo 'baseurl=http://\"${var.package_repository}\".s3-website.\"${var.vpc_region}\".amazonaws.com/\"${var.scale_version}\"/zimon_rpms/rhel9/' >> /etc/yum.repos.d/scale.repo\"",
      "sudo sh -c \"echo 'enabled=1' >> /etc/yum.repos.d/scale.repo\"",
      "sudo sh -c \"echo 'gpgcheck=1' >> /etc/yum.repos.d/scale.repo\"",
      "sudo sh -c \"echo 'gpgkey=http://\"${var.package_repository}\".s3-website.\"${var.vpc_region}\".amazonaws.com/\"${var.scale_version}\"/Public_Keys/Storage_Scale_public_key.pgp' >> /etc/yum.repos.d/scale.repo\"",
      "fi",
      "sudo dnf install gpfs* -y",
      "sudo /usr/lpp/mmfs/bin/mmbuildgpl",
      "sudo sh -c \"echo 'export PATH=$PATH:$HOME/bin:/usr/lpp/mmfs/bin' >> /root/.bashrc\"",
      "sudo rm -rf /etc/yum.repos.d/scale.repo",
      "sudo rm -rf /root/.bash_history",
      "sudo rm -rf /home/ec2-user/.bash_history"
    ]
  }

  post-processor "manifest" {
    output     = "${local.manifest_path}/manifest.json"
    strip_path = true
  }
}
