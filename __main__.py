import pulumi
import pulumi_aws as aws
import ipaddress

# Helper function to calculate subnet CIDR blocks based on the VPC's CIDR (/16)
def get_subnet_cidr(vpc_cidr, subnet_offset):
    network = ipaddress.IPv4Network(vpc_cidr)
    subnet = network.subnets(new_prefix=24)  # Assuming /24 subnets within the /16 VPC
    return str(list(subnet)[subnet_offset])

# Common Tags
def common_tags(env):
    return {"Environment": env, "Project": "bwiseth"}

def create_vpc_environment(name, cidr_block):
    # Create VPC
    vpc = aws.ec2.Vpc(f"{name}-vpc",
                      cidr_block=cidr_block,
                      enable_dns_support=True,
                      enable_dns_hostnames=True,
                      tags={**common_tags(name), "Name": f"{name}-vpc"})

    # Get available availability zones dynamically
    zones = aws.get_availability_zones(state="available").names

    # Create subnets
    public_subnet1 = aws.ec2.Subnet(f"{name}-public-subnet1",
                                    vpc_id=vpc.id,
                                    cidr_block=get_subnet_cidr(cidr_block, 1),
                                    availability_zone=zones[0],
                                    map_public_ip_on_launch=True,
                                    tags={**common_tags(name), "Name": f"{name}-public-subnet1"})

    public_subnet2 = aws.ec2.Subnet(f"{name}-public-subnet2",
                                    vpc_id=vpc.id,
                                    cidr_block=get_subnet_cidr(cidr_block, 2),
                                    availability_zone=zones[1],
                                    map_public_ip_on_launch=True,
                                    tags={**common_tags(name), "Name": f"{name}-public-subnet2"})

    private_subnet1 = aws.ec2.Subnet(f"{name}-private-subnet1",
                                     vpc_id=vpc.id,
                                     cidr_block=get_subnet_cidr(cidr_block, 3),
                                     availability_zone=zones[0],
                                     tags={**common_tags(name), "Name": f"{name}-private-subnet1"})

    private_subnet2 = aws.ec2.Subnet(f"{name}-private-subnet2",
                                     vpc_id=vpc.id,
                                     cidr_block=get_subnet_cidr(cidr_block, 4),
                                     availability_zone=zones[1],
                                     tags={**common_tags(name), "Name": f"{name}-private-subnet2"})

    # Create Internet Gateway
    internet_gateway = aws.ec2.InternetGateway(f"{name}-igw",
                                               vpc_id=vpc.id,
                                               tags={**common_tags(name), "Name": f"{name}-igw"})

    # Create EIPs for NAT Gateway
    eip1 = aws.ec2.Eip(f"{name}-eip1", vpc=True)
    eip2 = aws.ec2.Eip(f"{name}-eip2", vpc=True)

    # Create NAT Gateway
    nat_gateway1 = aws.ec2.NatGateway(f"{name}-nat-gateway1",
                                      subnet_id=public_subnet1.id,
                                      allocation_id=eip1.id,
                                      tags={**common_tags(name), "Name": f"{name}-nat-gateway1"},
                                      depends_on=[internet_gateway])

    nat_gateway2 = aws.ec2.NatGateway(f"{name}-nat-gateway2",
                                      subnet_id=public_subnet2.id,
                                      allocation_id=eip2.id,
                                      tags={**common_tags(name), "Name": f"{name}-nat-gateway2"},
                                      depends_on=[internet_gateway])

    # Create Route Tables
    public_rt = aws.ec2.RouteTable(f"{name}-public-rt",
                                   vpc_id=vpc.id,
                                   routes=[aws.ec2.RouteTableRouteArgs(
                                       cidr_block="0.0.0.0/0",
                                       gateway_id=internet_gateway.id
                                   )],
                                   tags={**common_tags(name), "Name": f"{name}-public-rt"})

    private_rt = aws.ec2.RouteTable(f"{name}-private-rt",
                                    vpc_id=vpc.id,
                                    tags={**common_tags(name), "Name": f"{name}-private-rt"})

    aws.ec2.RouteTableAssociation(f"{name}-public-rt-assoc1",
                                  subnet_id=public_subnet1.id,
                                  route_table_id=public_rt.id)

    aws.ec2.RouteTableAssociation(f"{name}-public-rt-assoc2",
                                  subnet_id=public_subnet2.id,
                                  route_table_id=public_rt.id)

    aws.ec2.RouteTableAssociation(f"{name}-private-rt-assoc1",
                                  subnet_id=private_subnet1.id,
                                  route_table_id=private_rt.id)

    aws.ec2.RouteTableAssociation(f"{name}-private-rt-assoc2",
                                  subnet_id=private_subnet2.id,
                                  route_table_id=private_rt.id)

    # Add Private Route for Internet traffic via NAT Gateway
    aws.ec2.Route(f"{name}-private-route1",
                  route_table_id=private_rt.id,
                  destination_cidr_block="0.0.0.0/0",
                  nat_gateway_id=nat_gateway1.id,
                  depends_on=[nat_gateway1])

    aws.ec2.Route(f"{name}-private-route2",
                  route_table_id=private_rt.id,
                  destination_cidr_block="0.0.0.0/0",
                  nat_gateway_id=nat_gateway2.id,
                  depends_on=[nat_gateway2])

    # Security Groups
    public_sg = aws.ec2.SecurityGroup(f"{name}-public-sg",
                                      vpc_id=vpc.id,
                                      description="Allow HTTP and HTTPS inbound",
                                      ingress=[
                                          aws.ec2.SecurityGroupIngressArgs(
                                              protocol="tcp",
                                              from_port=80,
                                              to_port=80,
                                              cidr_blocks=["0.0.0.0/0"]),
                                          aws.ec2.SecurityGroupIngressArgs(
                                              protocol="tcp",
                                              from_port=443,
                                              to_port=443,
                                              cidr_blocks=["0.0.0.0/0"])
                                      ],
                                      egress=[
                                          aws.ec2.SecurityGroupEgressArgs(
                                              protocol="-1",
                                              from_port=0,
                                              to_port=0,
                                              cidr_blocks=["0.0.0.0/0"])
                                      ],
                                      tags={**common_tags(name), "Name": f"{name}-public-sg"})

    private_sg = aws.ec2.SecurityGroup(f"{name}-private-sg",
                                       vpc_id=vpc.id,
                                       description="Allow internal service-to-service communication",
                                       ingress=[
                                           aws.ec2.SecurityGroupIngressArgs(
                                               protocol="tcp",
                                               from_port=0,
                                               to_port=65535,
                                               cidr_blocks=[cidr_block])
                                       ],
                                       egress=[
                                           aws.ec2.SecurityGroupEgressArgs(
                                               protocol="-1",
                                               from_port=0,
                                               to_port=0,
                                               cidr_blocks=["0.0.0.0/0"])
                                       ],
                                       tags={**common_tags(name), "Name": f"{name}-private-sg"})

    # Export relevant IDs and outputs for cross-stack references
    pulumi.export(f"{name}_vpc_id", vpc.id)
    pulumi.export(f"{name}_public_subnets", [public_subnet1.id, public_subnet2.id])
    pulumi.export(f"{name}_private_subnets", [private_subnet1.id, private_subnet2.id])
    pulumi.export(f"{name}_nat_gateway_ids", [nat_gateway1.id, nat_gateway2.id])

# Create dev environment
create_vpc_environment("bwiseth_dev", "10.0.0.0/16")

# Create prod environment
create_vpc_environment("bwiseth_prod", "10.1.0.0/16")