import boto3
import os

ec2 = boto3.client("ec2")

# Set this environment variable to "true" only when you want deletion.
DELETE_SNAPSHOTS = os.environ.get("DELETE_SNAPSHOTS", "false").lower() == "true"


def lambda_handler(event, context):

    print("Starting stale EBS snapshot cleanup...")

    # ---------------------------------------------------------
    # 1. Get all EBS snapshots owned by this AWS account
    # ---------------------------------------------------------
    snapshots_response = ec2.describe_snapshots(
        OwnerIds=["self"]
    )

    snapshots = snapshots_response.get("Snapshots", [])

    print(f"Total snapshots found: {len(snapshots)}")

    # ---------------------------------------------------------
    # 2. Get all EC2 instances that are running or stopped
    # ---------------------------------------------------------
    instances_response = ec2.describe_instances(
        Filters=[
            {
                "Name": "instance-state-name",
                "Values": ["running", "stopped"]
            }
        ]
    )

    active_volume_ids = set()

    # ---------------------------------------------------------
    # 3. Collect EBS volumes attached to active instances
    # ---------------------------------------------------------
    for reservation in instances_response.get("Reservations", []):

        for instance in reservation.get("Instances", []):

            for block_device in instance.get("BlockDeviceMappings", []):

                ebs = block_device.get("Ebs")

                if ebs and ebs.get("VolumeId"):
                    active_volume_ids.add(ebs["VolumeId"])

    print(
        f"Total EBS volumes attached to running/stopped instances: "
        f"{len(active_volume_ids)}"
    )

    stale_snapshots = []

    # ---------------------------------------------------------
    # 4. Identify stale snapshots
    # ---------------------------------------------------------
    for snapshot in snapshots:

        snapshot_id = snapshot["SnapshotId"]
        volume_id = snapshot.get("VolumeId")

        # Snapshot has no associated volume
        if not volume_id:
            stale_snapshots.append(snapshot_id)
            continue

        # Volume is not attached to any running/stopped instance
        if volume_id not in active_volume_ids:
            stale_snapshots.append(snapshot_id)

    print(f"Stale snapshots found: {len(stale_snapshots)}")

    # ---------------------------------------------------------
    # 5. Delete stale snapshots
    # ---------------------------------------------------------
    deleted_snapshots = []

    for snapshot_id in stale_snapshots:

        if DELETE_SNAPSHOTS:

            try:
                ec2.delete_snapshot(
                    SnapshotId=snapshot_id
                )

                deleted_snapshots.append(snapshot_id)

                print(f"Deleted stale snapshot: {snapshot_id}")

            except Exception as e:

                print(
                    f"Failed to delete snapshot "
                    f"{snapshot_id}: {str(e)}"
                )

        else:

            print(
                f"DRY RUN: Would delete snapshot {snapshot_id}"
            )

    # ---------------------------------------------------------
    # 6. Return summary
    # ---------------------------------------------------------
    return {
        "statusCode": 200,
        "body": {
            "total_snapshots": len(snapshots),
            "active_volumes": len(active_volume_ids),
            "stale_snapshots": len(stale_snapshots),
            "deleted_snapshots": len(deleted_snapshots),
            "delete_enabled": DELETE_SNAPSHOTS
        }
    }