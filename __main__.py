import pulumi
import pulumi_aws as aws
import ipaddress

# Helper function to calculate subnet CIDR blocks based on the VPC's CIDR (/16)
def get_subnet_cidr(vpc_cidr: str, subnet_offset: int) -> str:
    """
    Calculate subnet CIDR block based on the VPC's CIDR.

    Args:
        vpc_cidr (str): The VPC's CIDR block.
        subnet_offset (int): The subnet offset.

    Returns:
        str: The subnet CIDR block.
    """
    try:
        network = ipaddress.IPv4Network(vpc_cidr)
        subnets = list(network.subnets(new_prefix=24))  # Assuming /24 subnets within the /16 VPC
        return str(subnets[subnet_offset])
    except (IndexError, ValueError) as e:
        raise ValueError(f"Error calculating subnet CIDR: {e}")

# Common Tags
def common_tags(env: str) -> dict:
    """
    Return common tags for resources.

    Args:
        env (str): The environment.

    Returns:
        dict: A dictionary of common tags.
    """
    return {"Environment": env, "Project": "bwiseth"}

# Create VPC
def create_vpc(name: str, cidr_block: str) -> aws.ec2.Vpc:
    """
    Create a VPC.

    Args:
        name (str): The name of the VPC.
        cidr_block (str): The CIDR block of the VPC.

    Returns:
        aws.ec2.Vpc: The created VPC resource.
    """
    try:
        return aws.ec2.Vpc(
            f"{name}-vpc",
            cidr_block=cidr_block,
            enable_dns_support=True,
            enable_dns_hostnames=True,
            tags={**common_tags(name), "Name": f"{name}-vpc"},
        )
    except Exception as e:
        raise RuntimeError(f"Error creating VPC: {e}")

# Create Subnet
def create_subnet(
    name: str, vpc_id: str, cidr_block: str, availability_zone: str, map_public_ip: bool
) -> aws.ec2.Subnet:
    """
    Create a subnet.

    Args:
        name (str): The name of the subnet.
        vpc_id (str): The ID of the VPC.
        cidr_block (str): The CIDR block of the subnet.
        availability_zone (str): The availability zone for the subnet.
        map_public_ip (bool): Whether to map public IP on launch.

    Returns:
        aws.ec2.Subnet: The created subnet resource.
    """
    try:
        return aws.ec2.Subnet(
            f"{name}-subnet",
            vpc_id=vpc_id,
            cidr_block=cidr_block,
            availability_zone=availability_zone,
            map_public_ip_on_launch=map_public_ip,
            tags={**common_tags(name), "Name": f"{name}-subnet"},
        )
    except Exception as e:
        raise RuntimeError(f"Error creating subnet: {e}")

# Create Internet Gateway
def create_internet_gateway(name: str, vpc_id: str) -> aws.ec2.InternetGateway:
    """
    Create an Internet Gateway.

    Args:
        name (str): The name of the Internet Gateway.
        vpc_id (str): The ID of the VPC.

    Returns:
        aws.ec2.InternetGateway: The created Internet Gateway resource.
    """
    try:
        return aws.ec2.InternetGateway(
            f"{name}-igw",
            vpc_id=vpc_id,
            tags={**common_tags(name), "Name": f"{name}-igw"},
        )
    except Exception as e:
        raise RuntimeError(f"Error creating Internet Gateway: {e}")

# Create NAT Gateway
def create_nat_gateway(
    name: str, subnet_id: str, allocation_id: str, dependencies
) -> aws.ec2.NatGateway:
    """
    Create a NAT Gateway.

    Args:
        name (str): The name of the NAT Gateway.
        subnet_id (str): The ID of the subnet.
        allocation_id (str): The ID of the Elastic IP allocation.
        dependencies: Dependencies for the resource.

    Returns:
        aws.ec2.NatGateway: The created NAT Gateway resource.
    """
    try:
        return aws.ec2.NatGateway(
            f"{name}-nat-gateway",
            subnet_id=subnet_id,
            allocation_id=allocation_id,
            tags={**common_tags(name), "Name": f"{name}-nat-gateway"},
            opts=pulumi.ResourceOptions(depends_on=dependencies),  # Corrected usage
        )
    except Exception as e:
        raise RuntimeError(f"Error creating NAT Gateway: {e}")

# Create VPC Environment
def create_vpc_environment(name: str, cidr_block: str) -> None:
    """
    Create a VPC environment.

    Args:
        name (str): The name of the VPC.
        cidr_block (str): The CIDR block of the VPC.
    """
    try:
        vpc = create_vpc(name, cidr_block)

        zones = aws.get_availability_zones(state="available").names
        if len(zones) < 2:
            raise RuntimeError("Not enough availability zones available.")

        public_subnet1 = create_subnet(
            f"{name}-public-subnet1",
            vpc.id,
            get_subnet_cidr(cidr_block, 1),
            zones[0],
            True,
        )
        public_subnet2 = create_subnet(
            f"{name}-public-subnet2",
            vpc.id,
            get_subnet_cidr(cidr_block, 2),
            zones[1],
            True,
        )

        private_subnet1 = create_subnet(
            f"{name}-private-subnet1",
            vpc.id,
            get_subnet_cidr(cidr_block, 3),
            zones[0],
            False,
        )
        private_subnet2 = create_subnet(
            f"{name}-private-subnet2",
            vpc.id,
            get_subnet_cidr(cidr_block, 4),
            zones[1],
            False,
        )

        internet_gateway = create_internet_gateway(name, vpc.id)

        eip1 = aws.ec2.Eip(f"{name}-eip1", domain="vpc")  # Corrected parameter
        eip2 = aws.ec2.Eip(f"{name}-eip2", domain="vpc")  # Corrected parameter

        nat_gateway1 = create_nat_gateway(
            f"{name}-nat-gateway1",
            public_subnet1.id,
            eip1.allocation_id,
            dependencies=[internet_gateway],
        )
        nat_gateway2 = create_nat_gateway(
            f"{name}-nat-gateway2",
            public_subnet2.id,
            eip2.allocation_id,
            dependencies=[internet_gateway],
        )

        # Export relevant IDs and outputs for cross-stack references
        pulumi.export(f"{name}_vpc_id", vpc.id)
        pulumi.export(f"{name}_public_subnets", [public_subnet1.id, public_subnet2.id])
        pulumi.export(
            f"{name}_private_subnets", [private_subnet1.id, private_subnet2.id]
        )
        pulumi.export(
            f"{name}_nat_gateway_ids", [nat_gateway1.id, nat_gateway2.id]
        )
    except Exception as e:
        raise RuntimeError(f"Error creating VPC environment: {e}")

# Get stack name and CIDR block
name = pulumi.get_stack()
cidr_block = pulumi.Config().get("cidr_block") or "10.0.0.0/16"  # Set default CIDR block

# Create stack environment
create_vpc_environment(name, cidr_block)